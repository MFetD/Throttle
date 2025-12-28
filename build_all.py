#!/usr/bin/env python3
"""
build_all.py
------------
Cross-platform PyInstaller build script for Throttle.
Bundles:
  - throttleW.py (main GUI)
  - bandwidth_proxy.py (proxy backend)
Outputs:
  - throttle.zip (Windows)
  - Throttle.dmg (macOS)
"""

import os
import platform
import subprocess
import shutil
import sys
from pathlib import Path

APP_NAME = "Throttle"
MAIN_SCRIPT = "throttleW.py"
PROXY_SCRIPT = "bandwidth_proxy.py"
ICON_WIN = "throttle.ico"
ICON_MAC = "throttle.icns"
IMAGE_FILE = "throttle.png"

# -------------------------------------------------------------
def run(cmd, cwd=None):
    """Run a command safely and exit on error."""
    print(f"\n🛠️  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, shell=False)
    if result.returncode != 0:
        sys.exit(f"❌ Build step failed: {' '.join(cmd)}")

def ensure_exists(path):
    """Ensure a required file exists before building."""
    if not os.path.exists(path):
        sys.exit(f"❌ Missing required file: {path}")

def clean():
    """Remove previous build artifacts."""
    print("\n🧹 Cleaning old build artifacts...")
    for folder in ("build", "dist", "__pycache__"):
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)

# -------------------------------------------------------------
def build_windows():
    print("\n💻 Building Windows version...")
    ensure_exists(MAIN_SCRIPT)
    ensure_exists(PROXY_SCRIPT)
    ensure_exists(ICON_WIN)
    ensure_exists(IMAGE_FILE)

    # On Windows, PyInstaller uses ';' to separate add-data pairs
    cmd = [
        "pyinstaller", "--onefile", "--noconsole",
        "--name", APP_NAME.lower(),
        "--icon", ICON_WIN,
        "--add-data", f"{IMAGE_FILE};.",
        "--add-data", f"{PROXY_SCRIPT.replace('.py', '.exe')};.",
        MAIN_SCRIPT
    ]
    run(cmd)

    dist_exe = Path("dist") / f"{APP_NAME.lower()}.exe"
    if not dist_exe.exists():
        sys.exit("❌ Build failed: throttle.exe not found")

    print("\n📦 Creating ZIP package...")
    shutil.make_archive(APP_NAME.lower(), 'zip', "dist", dist_exe.name)
    print(f"✅ Windows build complete: {APP_NAME.lower()}.zip")

# -------------------------------------------------------------
def build_mac():
    print("\n🍎 Building macOS version...")
    ensure_exists(MAIN_SCRIPT)
    ensure_exists(PROXY_SCRIPT)
    ensure_exists(ICON_MAC)
    ensure_exists(IMAGE_FILE)

    # On macOS/Linux, PyInstaller uses ':' instead of ';'
    cmd = [
        "pyinstaller", "--onefile", "--windowed",
        "--name", APP_NAME,
        "--icon", ICON_MAC,
        "--add-data", f"{IMAGE_FILE}:.",
        "--add-data", f"{PROXY_SCRIPT}:.",
        MAIN_SCRIPT
    ]
    run(cmd)

    dist_app = Path("dist") / f"{APP_NAME}.app"
    if not dist_app.exists():
        sys.exit("❌ Build failed: Throttle.app not found")

    dmg_name = f"{APP_NAME}.dmg"
    print("\n📦 Creating DMG package...")
    if shutil.which("create-dmg") is None:
        print("⚠️  create-dmg not found. Install it with: brew install create-dmg")
    else:
        run(["create-dmg", dmg_name, str(dist_app)])
        print(f"✅ macOS build complete: {dmg_name}")

# -------------------------------------------------------------
def main():
    clean()
    sys_os = platform.system().lower()

    if sys_os == "windows":
        build_windows()
    elif sys_os == "darwin":
        build_mac()
    else:
        sys.exit("❌ Unsupported OS for packaging (build on Windows or macOS).")

    print("\n🎉 All done! Distributables are ready in /dist")

if __name__ == "__main__":
    main()
