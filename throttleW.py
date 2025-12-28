#!/usr/bin/env python3
"""
Throttle GUI v5 — Final Stable Version
--------------------------------------
Combines modern GUI styling, safe PowerShell process handling,
and silent background proxy execution.
"""

import os
import sys
import subprocess
import threading
import time
import psutil
import tkinter as tk
from tkinter import ttk, messagebox
import socket
import tempfile
import shutil
from pathlib import Path 
import platform, time
import traceback

def get_proxy_path():
    """
    Return the correct proxy path based on platform and build type.
    - On Windows: use bundled bandwidth_proxy.exe
    - On macOS/Linux: use bundled bandwidth_proxy.py (or binary if built)
    """
    

    # Determine runtime base directory (PyInstaller or local)
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.argv[0])))
    sys_os = platform.system().lower()

    exe_proxy = os.path.join(base, "bandwidth_proxy.exe")
    bin_proxy = os.path.join(base, "bandwidth_proxy")
    py_proxy = os.path.join(base, "bandwidth_proxy.py")

    # --- Windows build: prefer .exe ---
    if sys_os == "windows" and os.path.exists(exe_proxy):
        return exe_proxy

    # --- macOS/Linux build: prefer .py, fallback to compiled binary ---
    if os.path.exists(py_proxy):
        return py_proxy
    if os.path.exists(bin_proxy):
        return bin_proxy

    # --- Fallback (development mode) ---
    return exe_proxy if sys_os == "windows" else py_proxy






def find_browsers():
    """Locate common browsers on Windows and macOS."""
    paths = {}
    sys_os = platform.system().lower()

    if sys_os == "windows":
        common = {
            "Edge": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ],
            "Chrome": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ],
            "Brave": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
            ],
            "Firefox": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
            ],
            "Tor": [
                r"C:\Program Files\Tor Browser\Browser\firefox.exe",
                r"C:\Program Files (x86)\Tor Browser\Browser\firefox.exe",
            ],
            "DuckDuckGo": [
                r"C:\Program Files\DuckDuckGo\DuckDuckGo Browser\Application\duckduckgo.exe",
                r"C:\Program Files (x86)\DuckDuckGo\DuckDuckGo Browser\Application\duckduckgo.exe",
            ],
            "Safari": [],  # Safari not on Windows
        }

    elif sys_os == "darwin":  # macOS
        common = {
            "Safari": ["/Applications/Safari.app/Contents/MacOS/Safari"],
            "Chrome": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
            "Brave": ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"],
            "Edge": ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
            "Firefox": ["/Applications/Firefox.app/Contents/MacOS/firefox"],
            "DuckDuckGo": ["/Applications/DuckDuckGo.app/Contents/MacOS/DuckDuckGo"],
            "Tor": ["/Applications/Tor Browser.app/Contents/MacOS/firefox"],
        }
    else:
        common = {}

    for name, guesses in common.items():
        for g in guesses:
            if os.path.exists(g):
                paths[name] = g
                break
    return paths



class ThrottleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Throttle Test Environment")
        self.root.geometry("680x560")
        self.root.resizable(False, False)
        self.proxy_proc = None
        self.browser_paths = find_browsers()
        self.current_port = 8888

        style = ttk.Style()
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        style.configure("TEntry", font=("Segoe UI", 10))

        frm = ttk.Frame(root, padding=20)
        frm.pack(fill="both", expand=True)
        frm.grid_rowconfigure(7, weight=1)
        frm.grid_columnconfigure(0, weight=1)

        # Input fields
        ttk.Label(frm, text="Upload (kbps):").grid(row=0, column=0, sticky="e", pady=5)
        ttk.Label(frm, text="Download (kbps):").grid(row=1, column=0, sticky="e", pady=5)
        ttk.Label(frm, text="Calibration (×):").grid(row=2, column=0, sticky="e", pady=5)

        self.up_var = tk.StringVar(value="200")
        self.down_var = tk.StringVar(value="500")
        self.calib_var = tk.StringVar(value="1.0")

        ttk.Entry(frm, textvariable=self.up_var, width=12).grid(row=0, column=1, sticky="w")
        ttk.Entry(frm, textvariable=self.down_var, width=12).grid(row=1, column=1, sticky="w")
        ttk.Entry(frm, textvariable=self.calib_var, width=12).grid(row=2, column=1, sticky="w")

        self.preset_combo = ttk.Combobox(
            frm,
            values=["1.0 (None)", "2.0 (Light PC)", "3.0 (Win64 fast)"],
            state="readonly",
            width=18,
        )
        self.preset_combo.grid(row=3, column=1, sticky="w")
        self.preset_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: self.calib_var.set(self.preset_combo.get().split()[0]),
        )

        ttk.Button(frm, text="Start Proxy", command=self.start_proxy).grid(
            row=4, column=0, pady=10
        )
        ttk.Button(frm, text="Stop Proxy", command=self.stop_proxy).grid(
            row=4, column=1, pady=10
        )

        ttk.Label(frm, text="Launch Browser:").grid(row=5, column=0, sticky="e", pady=5)
        self.browser_combo = ttk.Combobox(
            frm, values=list(self.browser_paths.keys()) or ["None found"], state="readonly"
        )
        self.browser_combo.grid(row=5, column=1, sticky="w")
        if self.browser_paths:
            self.browser_combo.current(0)

        ttk.Button(frm, text="Open Throttled Browser", command=self.open_browser).grid(
            row=6, column=0, columnspan=2, pady=10
        )

        self.status = ttk.Label(frm, text="Idle", foreground="gray")
        self.status.grid(row=7, column=0, columnspan=2, pady=10)

        # Log window
        log_frame = ttk.LabelFrame(frm, text="Proxy Log")
        log_frame.grid(row=8, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        self.log_text = tk.Text(log_frame, height=8, width=60, wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "Logs will appear here...\n")
        self.log_text.configure(state="disabled")

    

    def find_free_port(self, preferred=8888):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('127.0.0.1', preferred))
            port = sock.getsockname()[1]
        except OSError:
            sock.bind(('127.0.0.1', 0))  # 0 = ask OS for free port
            port = sock.getsockname()[1]
        finally:
            sock.close()
        return port
    
    def launch_proxy_silent(self, proxy_exe, port, adj_up, adj_down):
        """Launch bandwidth_proxy safely and silently via PowerShell (Windows) or subprocess (macOS/Linux)."""
        

        sys_os = platform.system().lower()
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.argv[0])))
        proxy_exe = os.path.join(base_dir, os.path.basename(proxy_exe))
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell"

        try:
            if sys_os == "windows":
                if not os.path.isfile(proxy_exe):
                    self.append_log(f"[ERROR] Proxy not found: {proxy_exe}\n")
                    return None

                # build argument list PowerShell-safe
                arglist = f"'--port','{port}','--up','{adj_up}','--down','{adj_down}'"

                ps_cmd = [
                    pwsh, "-NoProfile", "-Command",
                    (
                        f'Start-Process -WindowStyle Hidden '
                        f'-WorkingDirectory "{base_dir}" '
                        f'-FilePath "{proxy_exe}" '
                        f'-ArgumentList {arglist}'
                    )
                ]

                self.append_log(f"[INFO] Launching proxy via {pwsh}\n")
                return subprocess.Popen(ps_cmd, shell=False, creationflags=subprocess.CREATE_NO_WINDOW)

            elif sys_os in ("darwin", "linux"):
                cmd = [proxy_exe, "--port", str(port), "--up", str(adj_up), "--down", str(adj_down)]
                return subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid,
                    cwd=base_dir,
                    close_fds=True,
                )

            else:
                self.append_log(f"[ERROR] Unsupported OS: {sys_os}\n")
                return None

        except Exception:
            self.append_log(f"[FATAL] Proxy launch error:\n{traceback.format_exc()}\n")
            return None








    # ---------------------------------------------------------
    def start_proxy(self):  
        """Start or restart bandwidth proxy silently."""
        # If 8888 is in use, stop old proxy first
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        in_use = sock.connect_ex(('127.0.0.1', 8888)) == 0
        sock.close()
        if in_use:
            self.append_log("Port 8888 already active; stopping old proxy first...\n")
            self.stop_proxy()
            time.sleep(0.5)

        # Kill any orphaned bandwidth_proxy processes
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and p.info["name"].lower().startswith("bandwidth_proxy"):
                    p.terminate()
            except Exception:
                pass
        time.sleep(0.3)

        # Avoid duplicates
        if self.proxy_proc and self.proxy_proc.poll() is None:
            messagebox.showinfo("Proxy", "Proxy is already running.")
            return

        proxy_exe = get_proxy_path()
        if not os.path.exists(proxy_exe):
            messagebox.showerror("Error", f"bandwidth_proxy not found at {proxy_exe}")
            return

        try:
            up = float(self.up_var.get())
            down = float(self.down_var.get())
            cal = max(0.1, float(self.calib_var.get()))
        except ValueError:
            messagebox.showerror("Error", "Upload/Download/Calibration must be numbers.")
            return

        #    scale and clamp to ≥1 kbps; pass ints
        adj_up = max(1, int(round(up / cal)))
        adj_down = max(1, int(round(down / cal)))

        # choose a port (prefer 8888)
        self.current_port = self.find_free_port(8888)
        self.append_log(f"Using port {self.current_port} for proxy. (UP={adj_up} kbps, DOWN={adj_down} kbps)\n")

        # --- Launch silently via our helper ---
        self.proxy_proc = self.launch_proxy_silent(proxy_exe, self.current_port, adj_up, adj_down)

        if not self.proxy_proc:
            messagebox.showerror("Launch Error", "Proxy failed to start.")
            return

        # Wait briefly and confirm it’s listening
        for _ in range(10):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                if s.connect_ex(("127.0.0.1", self.current_port)) == 0:
                    break
            finally:
                s.close()
            time.sleep(0.1)
        else:
            self.append_log("Warning: proxy didn’t open its port yet.\n")

        self.status.config(text="Proxy running ✅", foreground="green")
        self.append_log("Proxy launched silently.\n")


    # ---------------------------------------------------------
    def stop_proxy(self):
        

        sys_os = platform.system().lower()
        pwsh = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        killed = False

        if sys_os == "windows":
            # 1️⃣  Find and kill whatever owns TCP port 8888
            stop_cmd = [
                pwsh, "-NoProfile", "-Command",
                (
                    "$p = netstat -ano | "
                    "Select-String ':8888 ' | "
                    "ForEach-Object { ($_ -split ' +')[-1] } | "
                    "Select-Object -Unique; "
                    "if ($p) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }"
                )
            ]
            try:
                subprocess.run(stop_cmd, shell=False,
                            creationflags=subprocess.CREATE_NO_WINDOW)
                killed = True
            except Exception as e:
                self.append_log(f"[ERROR] PowerShell stop failed: {e}\n")

        else:
            import psutil
            for p in psutil.process_iter(["pid", "name", "connections"]):
                for c in p.connections(kind="inet"):
                    if c.laddr.port == 8888:
                        p.terminate()
                        killed = True

        # verify closure
        time.sleep(0.5)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        still_open = s.connect_ex(("127.0.0.1", 8888)) == 0
        s.close()

        if still_open:
            self.append_log("[WARN] port 8888 still bound!\n")
            self.status.config(text="Port 8888 still active", foreground="orange")
        else:
            self.append_log("[OK] port 8888 freed.\n")
            self.status.config(text="Proxy stopped", foreground="red")



    # ---------------------------------------------------------
    def open_browser(self):
        """Cross-platform browser launch with proxy awareness."""
        choice = self.browser_combo.get()
        exe = self.browser_paths.get(choice)
        if not exe:
            messagebox.showerror("Browser not found", "No browser selected or found.")
            return

        port = getattr(self, "current_port", 8888)
        sys_os = platform.system().lower()
        proxy_arg = f"--proxy-server=http://127.0.0.1:{port}"

        try:
            # Safari / macOS native fallback (no CLI proxy support)
            if choice == "Safari":
                if sys_os == "darwin":
                    subprocess.Popen(["open", "-a", "Safari", "http://127.0.0.1"])
                    messagebox.showinfo(
                        "Safari Notice",
                        f"Safari ignores CLI proxy flags.\nSet proxy manually to 127.0.0.1:{port}."
                    )
                else:
                    messagebox.showinfo("Notice", "Safari not available on this OS.")
                return

            temp_profile = None
            try:
                temp_profile = tempfile.mkdtemp(prefix="throttle_profile_")
            except Exception:
                pass

            args = [exe, "--disable-quic", proxy_arg, "--no-first-run", "--new-window"]
            if temp_profile:
                args.append(f"--user-data-dir={temp_profile}")

            # macOS browsers are .app bundles, open with `open -a`
            if sys_os == "darwin" and exe.endswith(".app"):
                subprocess.Popen(["open", "-a", exe])
            else:
                subprocess.Popen(args, shell=False)

            self.append_log(f"Launched {choice} via proxy port {port}\n")
            self.status.config(text=f"{choice} launched", foreground="blue")

            if temp_profile:
                def cleanup():
                    shutil.rmtree(temp_profile, ignore_errors=True)
                self.root.protocol("WM_DELETE_WINDOW", lambda: (cleanup(), self.root.destroy()))

        except Exception as e:
            messagebox.showerror("Launch Error", str(e))
            self.append_log(f"Launch error: {e}\n")

    # ---------------------------------------------------------
    def append_log(self, line):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    ThrottleApp(root)
    root.mainloop()
