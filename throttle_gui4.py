#!/usr/bin/env python3
"""
Throttle GUI v4 — Safe, minimal, and bundling-ready.

✅ Launches bandwidth_proxy.exe in a hidden PowerShell window
✅ Opens browser (Edge/Chrome/Firefox) in a visible PowerShell window
✅ GUI kills ONLY the proxy PowerShell (not the browser)
✅ Prevents recursive spawning when bundled to .exe
✅ Requires bandwidth_proxy.exe to be in the same folder
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import psutil


class ThrottleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Throttle Test Environment")
        self.root.geometry("420x240")
        self.proxy_proc = None

        ttk.Label(root, text="Upload (kbps):").grid(row=0, column=0, sticky="e", pady=5)
        ttk.Label(root, text="Download (kbps):").grid(row=1, column=0, sticky="e", pady=5)
        self.up = tk.StringVar(value="200")
        self.down = tk.StringVar(value="500")
        ttk.Entry(root, textvariable=self.up, width=12).grid(row=0, column=1, sticky="w")
        ttk.Entry(root, textvariable=self.down, width=12).grid(row=1, column=1, sticky="w")

        ttk.Button(root, text="Start Proxy", command=self.start_proxy).grid(row=2, column=0, pady=8)
        ttk.Button(root, text="Stop Proxy", command=self.stop_proxy).grid(row=2, column=1, pady=8)
        ttk.Button(root, text="Open Browser", command=self.open_browser).grid(row=3, column=0, columnspan=2, pady=8)

        self.status = ttk.Label(root, text="Idle", foreground="gray")
        self.status.grid(row=4, column=0, columnspan=2, pady=5)

    # -------------------------------------------------------------
    def start_proxy(self):
        if self.proxy_proc and self.proxy_proc.poll() is None:
            messagebox.showinfo("Proxy", "Proxy is already running.")
            return

        proxy_exe = os.path.join(os.path.dirname(sys.argv[0]), "bandwidth_proxy.exe")
        if not os.path.exists(proxy_exe):
            messagebox.showerror("Error", f"bandwidth_proxy.exe not found in {os.path.dirname(sys.argv[0])}")
            return

        cmd = [
            "powershell",
            "-WindowStyle", "Hidden",
            "-Command",
            f"Start-Process -WindowStyle Hidden -FilePath '{proxy_exe}' "
            f"-ArgumentList '--port','8888','--up','{self.up.get()}','--down','{self.down.get()}'"
        ]

        try:
            # Start PowerShell host for the proxy
            self.proxy_proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            self.status.config(text="Proxy running", foreground="green")
        except Exception as e:
            messagebox.showerror("Launch Error", f"Failed to start proxy: {e}")

    # -------------------------------------------------------------
    def stop_proxy(self):
        killed = False
        # Kill proxy process directly
        if self.proxy_proc and self.proxy_proc.poll() is None:
            try:
                self.proxy_proc.terminate()
                killed = True
            except Exception:
                pass
            self.proxy_proc = None

        # Kill any orphaned PowerShell running bandwidth_proxy.exe
        for p in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if p.info["name"] and "powershell" in p.info["name"].lower():
                    if any("bandwidth_proxy.exe" in arg for arg in (p.info.get("cmdline") or [])):
                        p.terminate()
                        killed = True
            except Exception:
                continue

        if killed:
            self.status.config(text="Proxy stopped", foreground="red")
        else:
            self.status.config(text="No proxy running", foreground="gray")

    # -------------------------------------------------------------
    def open_browser(self):
        # pick any browser present
        candidates = [
            (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chrome --disable-quic"),
            (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "msedge --disable-quic"),
            (r"C:\Program Files\Mozilla Firefox\firefox.exe", "firefox"),
        ]
        browser = next((cmd for exe, cmd in candidates if os.path.exists(exe)), None)

        if not browser:
            messagebox.showerror("Error", "No supported browser found.")
            return

        try:
            subprocess.Popen([
                "powershell",
                "-NoExit",
                "-Command",
                f"start {browser} --proxy-server='http://127.0.0.1:8888'"
            ])
            self.status.config(text="Browser opened via proxy", foreground="blue")
        except Exception as e:
            messagebox.showerror("Browser Error", f"Could not open browser: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    ThrottleApp(root)
    root.mainloop()
