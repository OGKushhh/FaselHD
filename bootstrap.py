#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nfshd Bootstrap — First-run setup & launcher

On FIRST run:
  1. Downloads Python 3.12 embedded (~5 MB)
  2. Installs pip
  3. pip install requirements (~50 MB)
  4. playwright install chromium (~200 MB, auto only)
  5. Extracts nfshd.py + mini_player.py
  6. Launches FaselHD

On SUBSEQUENT runs:
  Skips setup → launches FaselHD instantly.

All files live in .faselhd_env/ next to the EXE.
To reset: delete .faselhd_env/ and re-run the EXE.
"""

import os
import sys
import zipfile
import subprocess
import urllib.request
import shutil
import hashlib

# ── Config ──────────────────────────────────────────────────────────────────
PYTHON_VERSION = "3.12.9"
PYTHON_SHORT = PYTHON_VERSION[:3]  # "3.12"
PYTHON_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

APP_FILES = ["nfshd.py", "mini_player.py", "requirements.txt"]

# ── Paths ───────────────────────────────────────────────────────────────────

def base_dir():
    """Directory where this EXE lives."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def env_dir():
    """Where Python + deps are installed."""
    return os.path.join(base_dir(), ".faselhd_env")


def app_dir():
    """Where nfshd.py + mini_player.py live."""
    return os.path.join(base_dir(), ".faselhd_app")


def bundled_path(name):
    """Path to a file bundled inside this EXE (sys._MEIPASS) or next to script."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(base_dir(), name)


def marker_path():
    return os.path.join(env_dir(), ".setup_done")


def version_marker():
    return os.path.join(env_dir(), ".setup_version")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _file_hash(path):
    """Quick MD5 hash of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _needs_reextract():
    """Check if bundled app files changed (new EXE version)."""
    ver_file = version_marker()
    exe_hash = _file_hash(sys.executable if getattr(sys, "frozen", False) else __file__)
    if os.path.isfile(ver_file):
        with open(ver_file) as f:
            return f.read().strip() != exe_hash
    return True


def download(url, dest):
    """Download a file with a progress bar."""
    name = url.split("/")[-1]
    print(f"\n  Downloading {name} ...")
    done = [0, 0]  # downloaded, total

    def _report(block, size, total):
        done[0] = block * size
        done[1] = total
        if total > 0:
            pct = min(done[0] * 100 // total, 100)
            mb = done[0] / 1048576
            print(f"\r  {mb:6.1f} MB  ({pct:3d}%)", end="", flush=True)

    urllib.request.urlretrieve(url, dest, _report)
    print()  # newline


def _pause(msg="Press Enter to exit ..."):
    if sys.platform == "win32":
        os.system("pause")
    else:
        input(msg)


# ── Setup ────────────────────────────────────────────────────────────────────

def setup():
    """Full first-time setup."""
    edir = env_dir()
    adir = app_dir()
    os.makedirs(edir, exist_ok=True)
    os.makedirs(adir, exist_ok=True)

    # ── 1. Python embedded ──
    py_zip = os.path.join(edir, "python.zip")
    download(PYTHON_URL, py_zip)

    print("  Extracting Python ...")
    with zipfile.ZipFile(py_zip) as zf:
        zf.extractall(edir)
    os.remove(py_zip)

    # ── 2. Enable site-packages (pip needs this) ──
    pth = os.path.join(edir, f"python{PYTHON_SHORT}._pth")
    if os.path.isfile(pth):
        with open(pth, "r") as f:
            lines = f.readlines()
        fixed = []
        for line in lines:
            if line.strip() == "#import site":
                fixed.append("import site\n")
            else:
                fixed.append(line)
        # Add app dir so 'import mini_player' works
        fixed.append(f"..\\{os.path.basename(adir)}\n")
        with open(pth, "w") as f:
            f.writelines(fixed)

    os.makedirs(os.path.join(edir, "Lib", "site-packages"), exist_ok=True)

    py = os.path.join(edir, "python.exe")

    # ── 3. pip ──
    gp = os.path.join(edir, "get-pip.py")
    download(GET_PIP_URL, gp)
    print("  Installing pip ...")
    subprocess.run(
        [py, gp, "--no-warn-script-location"],
        check=True, capture_output=True,
    )
    os.remove(gp)

    # ── 4. Requirements ──
    print("  Installing dependencies (1-3 min) ...")
    req = bundled_path("requirements.txt")
    subprocess.run(
        [py, "-m", "pip", "install", "-r", req,
         "--no-warn-script-location", "--no-cache-dir"],
        check=True,
    )

    # ── 5. Playwright Chromium ──
    print("  Installing Chromium browser ...")
    subprocess.run(
        [py, "-m", "playwright", "install", "chromium"],
        check=True,
    )

    # ── 6. Extract app files ──
    _extract_app_files()

    # ── 7. Mark done ──
    with open(marker_path(), "w") as f:
        f.write("done\n")
    exe_hash = _file_hash(sys.executable if getattr(sys, "frozen", False) else __file__)
    with open(version_marker(), "w") as f:
        f.write(exe_hash)

    print()
    print("  " + "=" * 48)
    print("    Setup complete!  FaselHD is ready.")
    print("  " + "=" * 48)
    print()


def _extract_app_files():
    """Copy/overwrite nfshd.py + mini_player.py + requirements.txt to app dir."""
    adir = app_dir()
    for name in APP_FILES:
        src = bundled_path(name)
        dst = os.path.join(adir, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)


# ── Launch ──────────────────────────────────────────────────────────────────

def launch():
    """Launch nfshd.py using the embedded Python."""
    py = os.path.join(env_dir(), "python.exe")
    script = os.path.join(app_dir(), "nfshd.py")

    if not os.path.isfile(py):
        print("  ERROR: Python not found. Delete .faselhd_env/ and re-run.")
        _pause()
        sys.exit(1)
    if not os.path.isfile(script):
        print("  ERROR: nfshd.py not found. Delete .faselhd_app/ and re-run.")
        _pause()
        sys.exit(1)

    os.chdir(app_dir())
    sys.exit(subprocess.run([py, script]).returncode)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    # Banner
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║   FaselHD  ·  by De3vil                ║")
    print("  ╚══════════════════════════════════════════╝")

    if not os.path.isfile(marker_path()):
        print("  First run — setting up environment ...")
        try:
            setup()
        except Exception as e:
            print(f"\n  Setup FAILED: {e}")
            print("  Fix: delete .faselhd_env/  then re-run this EXE.")
            _pause()
            sys.exit(1)
    else:
        # Re-extract app files if EXE was updated
        if _needs_reextract():
            print("  Updating app files ...")
            _extract_app_files()
            exe_hash = _file_hash(sys.executable if getattr(sys, "frozen", False) else __file__)
            with open(version_marker(), "w") as f:
                f.write(exe_hash)

    launch()


if __name__ == "__main__":
    main()
