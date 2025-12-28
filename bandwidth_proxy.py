#!/usr/bin/env python3
"""
Simple rate-limiting HTTP CONNECT tunneling proxy.

Usage:
    python3 bandwidth_proxy.py --port 8888 --up 100 --down 300

Meaning:
    --up 100    -> limit client -> server (upload) to 100 kbps
    --down 300  -> limit server -> client (download) to 300 kbps

Then point your browser to use HTTP proxy 127.0.0.1:8888
"""

import argparse
import asyncio
import time
from typing import Tuple

# Convert kilobits per second into bytes per second.  We use 1000 bits per
# kilobit as the unit in order to make the math simple.  An alternative would
# be 1024 but the difference is negligible for throttling purposes.
KBPS_TO_BPS = 1000


async def token_bucket_copy(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    rate_kbps: float,
    direction: str,
) -> None:
    """
    Copy data from reader to writer while limiting throughput.

    :param reader: An asyncio StreamReader from which to read bytes.
    :param writer: An asyncio StreamWriter to which to write bytes.
    :param rate_kbps: Limit in kilobits per second for this direction of traffic.
    :param direction: Label used in debugging. Not currently printed but kept
        for potential future use.

    This function implements a basic token bucket algorithm.  Tokens
    accumulate at a rate proportional to the configured throughput.  When
    transferring data, the loop only writes as many bytes as there are
    available tokens.  If no tokens remain, it waits briefly and
    accumulates more before proceeding.
    """
    # If the rate is zero or negative, we close the connection immediately.
    if rate_kbps <= 0:
        await writer.drain()
        writer.close()
        return

    # Convert kbps → bytes per second (1 kilobit = 1000 bits).  Divide by 8 to
    # convert bits to bytes.
    bytes_per_second = (rate_kbps * KBPS_TO_BPS) / 8.0
    # The maximum amount of data to send in a single chunk.  Using a
    # reasonably sized chunk reduces overhead without allowing large
    # bursts that circumvent the rate limit.
    max_chunk = 16 * 1024  # 16 KiB
    # Initialize token bucket with one second worth of allowance.  Starting
    # with a full bucket gives the connection a chance to perform any
    # protocol handshakes quickly.
    tokens = bytes_per_second
    last = time.monotonic()

    try:
        while True:
            data = await reader.read(8192)
            if not data:
                break
            idx = 0
            while idx < len(data):
                now = time.monotonic()
                elapsed = now - last
                last = now
                # Accumulate tokens according to elapsed time.
                tokens += elapsed * bytes_per_second
                # Cap tokens to at most two seconds worth of data to prevent
                # large bursts from building up if the connection goes idle.
                if tokens > 2 * bytes_per_second:
                    tokens = 2 * bytes_per_second

                allowed = int(min(tokens, max_chunk, len(data) - idx))
                if allowed <= 0:
                    # Not enough tokens to send even one byte.  Sleep briefly
                    # to allow token accumulation.  The sleep time here is
                    # intentionally small to provide responsive throttling.
                    await asyncio.sleep(0.01)
                    continue

                chunk = data[idx: idx + allowed]
                writer.write(chunk)
                try:
                    await writer.drain()
                except ConnectionResetError:
                    return
                idx += allowed
                tokens -= allowed
    except asyncio.CancelledError:
        # Propagate cancellation to allow graceful shutdown.
        raise
    except Exception:
        # Suppress any unexpected errors so that one bad connection does not
        # bring down the entire proxy.
        pass


async def handle_tunnel(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
    up_kbps: float,
    down_kbps: float,
) -> None:
    """
    Handle a CONNECT tunnel after the 200 response has been sent to the client.

    Once a CONNECT request has been acknowledged, this function opens a
    connection to the requested target and uses token_bucket_copy to
    bidirectionally pipe data.  Upload traffic (client→server) and download
    traffic (server→client) are rate limited separately using two tasks.
    """
    try:
        remote_reader, remote_writer = await asyncio.open_connection(target_host, target_port)
    except Exception:
        # If we cannot connect to the target, inform the client and bail.
        try:
            client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_writer.drain()
        except Exception:
            pass
        client_writer.close()
        return

    # Launch separate tasks for each direction of the tunnel.
    task_up = asyncio.create_task(token_bucket_copy(client_reader, remote_writer, up_kbps, "up"))
    task_down = asyncio.create_task(token_bucket_copy(remote_reader, client_writer, down_kbps, "down"))

    # Wait until either side finishes.  If one side closes, cancel the other
    # direction to terminate the tunnel completely.
    done, pending = await asyncio.wait([task_up, task_down], return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    try:
        remote_writer.close()
        client_writer.close()
    except Exception:
        pass


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    up_kbps: float,
    down_kbps: float,
) -> None:
    """
    Handle an incoming connection from a client.

    This function parses the initial HTTP request to determine whether the
    client is making a CONNECT request for an HTTPS tunnel or a normal HTTP
    request.  In the CONNECT case, it establishes a tunnel via handle_tunnel.
    For regular HTTP requests, it performs a simple proxy forward.
    """
    try:
        # Read the request line (e.g. "CONNECT example.com:443 HTTP/1.1").
        header = await reader.readuntil(b"\r\n")
    except Exception:
        writer.close()
        return
    first_line = header.decode(errors="ignore").strip()

    # Read all remaining request headers until a blank line.
    headers = header
    while True:
        try:
            line = await reader.readuntil(b"\r\n")
        except Exception:
            break
        headers += line
        if line == b"\r\n":
            break

    parts = first_line.split()
    if len(parts) < 2:
        writer.close()
        return

    method = parts[0].upper()
    target = parts[1]
    if method == "CONNECT":
        # CONNECT requests specify host:port.
        if ':' in target:
            host, port_str = target.split(':', 1)
            try:
                port = int(port_str)
            except Exception:
                port = 443
        else:
            host = target
            port = 443

        # Send a 200 response to signal the tunnel has been established.
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        await handle_tunnel(reader, writer, host, port, up_kbps, down_kbps)
    else:
        # For non-CONNECT requests, perform a very rudimentary forward.
        hdr_text = headers.decode(errors="ignore")
        host_header = None
        for line in hdr_text.split('\r\n'):
            if line.lower().startswith('host:'):
                host_header = line.split(':', 1)[1].strip()
                break
        if not host_header:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            writer.close()
            return

        target_host = host_header.split(':')[0]
        target_port = 80
        if ':' in host_header:
            try:
                target_port = int(host_header.split(':', 1)[1])
            except Exception:
                target_port = 80

        try:
            remote_reader, remote_writer = await asyncio.open_connection(target_host, target_port)
        except Exception:
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await writer.drain()
            writer.close()
            return

        # Forward the request headers to the remote server.
        remote_writer.write(headers)
        await remote_writer.drain()

        # Start tasks for forwarding data in both directions.
        task_up = asyncio.create_task(token_bucket_copy(reader, remote_writer, up_kbps, "up"))
        task_down = asyncio.create_task(token_bucket_copy(remote_reader, writer, down_kbps, "down"))

        done, pending = await asyncio.wait([task_up, task_down], return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

        try:
            remote_writer.close()
            writer.close()
        except Exception:
            pass


async def start_server(host: str, port: int, up_kbps: float, down_kbps: float) -> None:
    """Cross-platform start_server that retries if the port is busy."""
    for attempt in range(2):
        try:
            server = await asyncio.start_server(
                lambda r, w: handle_client(r, w, up_kbps, down_kbps),
                host,
                port,
                reuse_address=True,   # safe everywhere
            )
            break
        except OSError as e:
            if e.errno == 10048:        # “address already in use”
                if attempt == 0:
                    print(f"[!] Port {port} already in use. Retrying in 1 s...")
                    await asyncio.sleep(1)
                    continue
                print(f"[x] Port {port} is still in use. Another proxy running?")
                return
            raise

    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    print(f"[+] Proxy listening on {addrs}")

    async with server:
        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            pass
        finally:
            server.close()
            await server.wait_closed()
            print("[*] Proxy server shut down.")






def parse_args() -> Tuple[int, float, float, str]:
    """
    Parse command line arguments for the proxy.

    :return: A tuple containing the port, upload kbps, download kbps, and host.
    """
    ap = argparse.ArgumentParser(description="Simple bandwidth-limiting HTTP(S) proxy (CONNECT tunneling).")
    ap.add_argument("--host", default="127.0.0.1", help="Host to bind proxy (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8888, help="Port to bind proxy (default: 8888)")
    ap.add_argument("--up", type=float, default=1000.0, help="Upload limit in kbps (client->server). Default 1000 kbps")
    ap.add_argument("--down", type=float, default=1000.0, help="Download limit in kbps (server->client). Default 1000 kbps")
    args = ap.parse_args()
    return args.port, args.up, args.down, args.host


if __name__ == "__main__":
    port, up_kbps, down_kbps, host = parse_args()
    print(f"Starting proxy on {host}:{port}  |  upload={up_kbps} kbps  download={down_kbps} kbps")
    try:
        asyncio.run(start_server(host, port, up_kbps, down_kbps))
    except KeyboardInterrupt:
        print("Shutting down.")