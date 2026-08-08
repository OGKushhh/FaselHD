#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nfshd Bootstrap — First-run setup & launcher

On FIRST run:
  1. Check for system Python (3.10+) — use it if found
  2. Otherwise download Python 3.12 embedded (~5 MB)
  3. Check installed requirements — only install missing ones
  4. playwright install chromium if needed
  5. Extract nfshd.py + mini_player.py
  6. Launch FaselHD

On SUBSEQUENT runs:
  Skips setup → launches FaselHD instantly.

To reset: delete .faselhd_env/ and .faselhd_app/ next to the EXE.
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
MIN_PYTHON = (3, 10)

APP_FILES = ["nfshd.py", "mini_player.py", "requirements.txt"]

# ── Paths ───────────────────────────────────────────────────────────────────

def base_dir():
    """Directory where this EXE lives."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def env_dir():
    return os.path.join(base_dir(), ".faselhd_env")


def app_dir():
    return os.path.join(base_dir(), ".faselhd_app")


def bundled_path(name):
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, name)
    return os.path.join(base_dir(), name)


def marker_path():
    return os.path.join(env_dir(), ".setup_done")


def version_marker():
    return os.path.join(env_dir(), ".setup_version")


def python_marker():
    """Stores which Python path was chosen."""
    return os.path.join(env_dir(), ".python_path")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _file_hash(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _needs_reextract():
    ver_file = version_marker()
    exe_hash = _file_hash(sys.executable if getattr(sys, "frozen", False) else __file__)
    if os.path.isfile(ver_file):
        with open(ver_file) as f:
            return f.read().strip() != exe_hash
    return True


def download(url, dest):
    name = url.split("/")[-1]
    print(f"\n  Downloading {name} ...")
    done = [0, 0]

    def _report(block, size, total):
        done[0] = block * size
        done[1] = total
        if total > 0:
            pct = min(done[0] * 100 // total, 100)
            mb = done[0] / 1048576
            print(f"\r  {mb:6.1f} MB  ({pct:3d}%)", end="", flush=True)

    urllib.request.urlretrieve(url, dest, _report)
    print()


def _pause(msg="Press Enter to exit ..."):
    if sys.platform == "win32":
        os.system("pause")
    else:
        input(msg)


def _run(cmd, **kwargs):
    """Run a command and return returncode."""
    print(f"  > {' '.join(cmd)}")
    return subprocess.run(cmd, **kwargs).returncode


def _get_saved_python():
    """Return the saved Python path if it still exists."""
    pm = python_marker()
    if os.path.isfile(pm):
        with open(pm) as f:
            py = f.read().strip()
        if os.path.isfile(py):
            return py
    return None


# ── Find system Python ─────────────────────────────────────────────────────

def _check_python_version(py):
    """Check if a Python executable meets our minimum version. Returns version tuple or None."""
    try:
        r = subprocess.run(
            [py, "--version"], capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            return None
        # Output is like "Python 3.12.0"
        parts = r.stderr.strip().split() if r.stderr.strip() else r.stdout.strip().split()
        ver_str = parts[-1]  # "3.12.0"
        ver = tuple(int(x) for x in ver_str.split("."))
        return ver
    except Exception:
        return None


def _find_system_python():
    """Search for a usable system Python (3.10+). Returns path or None."""
    # On Windows, check common commands
    candidates = []
    if sys.platform == "win32":
        candidates = ["python", "python3", "py"]
        # Also check common install locations
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", "")
        for prefix in [
            os.path.join(local_app, "Programs", "Python"),
            os.path.join(program_files, "Python312"),
            os.path.join(program_files, "Python311"),
            os.path.join(program_files, "Python310"),
            program_files,
            program_files_x86,
        ]:
            if os.path.isdir(prefix):
                for entry in os.listdir(prefix):
                    full = os.path.join(prefix, entry)
                    if entry.lower().startswith("python") and os.path.isfile(full):
                        candidates.append(full)
    else:
        candidates = ["python3", "python"]

    for cmd in candidates:
        ver = _check_python_version(cmd)
        if ver and ver >= MIN_PYTHON:
            # Resolve to full path
            try:
                r = subprocess.run(
                    [sys.executable if os.path.isfile(sys.executable) else "python",
                     "-c",
                     f"import subprocess,shlex; p=subprocess.run(shlex.split('{cmd} --version'), capture_output=True, text=True, shell=False); print(p.stderr.strip() if p.stderr.strip() else p.stdout.strip())"],
                    capture_output=True, text=True, timeout=10
                )
            except Exception:
                continue
            # Try to get the actual executable path
            if os.path.isfile(cmd) and os.path.isabs(cmd):
                return cmd
            # Try shutil.which
            try:
                import shutil
                resolved = shutil.which(cmd)
                if resolved:
                    return resolved
            except Exception:
                pass

    return None


# ── Setup steps ──────────────────────────────────────────────────────────────

def _get_or_find_python():
    """Return Python path: saved → system → download embedded."""
    # 1. Check saved path
    saved = _get_saved_python()
    if saved:
        ver = _check_python_version(saved)
        if ver and ver >= MIN_PYTHON:
            return saved, "using cached"

    # 2. Check system Python
    sys_py = _find_system_python()
    if sys_py:
        ver = _check_python_version(sys_py)
        if ver and ver >= MIN_PYTHON:
            return sys_py, "using system Python"

    # 3. Download embedded Python
    return _download_embedded_python(), "downloaded embedded Python"


def _download_embedded_python():
    """Download and set up Python embedded. Returns python.exe path."""
    edir = env_dir()
    os.makedirs(edir, exist_ok=True)

    py_zip = os.path.join(edir, "python.zip")
    download(PYTHON_URL, py_zip)

    print("  Extracting Python ...")
    with zipfile.ZipFile(py_zip) as zf:
        zf.extractall(edir)
    os.remove(py_zip)

    # Enable site-packages
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
        # Add app dir to path
        fixed.append(f"..\\{os.path.basename(app_dir())}\n")
        with open(pth, "w") as f:
            f.writelines(fixed)

    os.makedirs(os.path.join(edir, "Lib", "site-packages"), exist_ok=True)

    py = os.path.join(edir, "python.exe")

    # Install pip
    gp = os.path.join(edir, "get-pip.py")
    download(GET_PIP_URL, gp)
    print("  Installing pip ...")
    subprocess.run(
        [py, gp, "--no-warn-script-location"],
        check=True, capture_output=True,
    )
    os.remove(gp)

    return py


def _check_missing_requirements(py):
    """Check which requirements are missing. Returns list of package names."""
    req_path = bundled_path("requirements.txt")
    if not os.path.isfile(req_path):
        return []

    missing = []
    try:
        result = subprocess.run(
            [py, "-m", "pip", "list", "--format=freeze"],
            capture_output=True, text=True, timeout=30
        )
        installed = {}
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if "==" in line:
                    name, _ = line.split("==", 1)
                    installed[name.lower().replace("-", "_")] = True

        with open(req_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Parse: "package>=1.0" → "package"
                pkg = line.split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip()
                if pkg.lower().replace("-", "_") not in installed:
                    missing.append(line)
    except Exception:
        # If we can't check, install everything
        return ["ALL"]

    return missing


def _check_chromium(py):
    """Check if Playwright Chromium is installed."""
    try:
        result = subprocess.run(
            [py, "-c",
             "from playwright.sync_api import sync_playwright;"
             "pw=sync_playwright().start();"
             "pw.chromium.launch(headless=True).close();"
             "pw.stop()"],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception:
        return False


# ── Full setup ──────────────────────────────────────────────────────────────

def setup():
    """Full first-time setup."""
    edir = env_dir()
    adir = app_dir()
    os.makedirs(edir, exist_ok=True)
    os.makedirs(adir, exist_ok=True)

    # ── 1. Find Python ──
    print()
    py, method = _get_or_find_python()
    print(f"  Python: {method} ({py})")
    print(f"  Version: {_check_python_version(py)}")

    # Save the chosen Python path
    with open(python_marker(), "w") as f:
        f.write(py)

    # ── 2. Check & install missing requirements ──
    print("\n  Checking installed packages ...")
    missing = _check_missing_requirements(py)

    if missing and missing != ["ALL"]:
        print(f"  Missing {len(missing)} package(s): {', '.join(missing[:5])}"
              + (f" +{len(missing)-5} more" if len(missing) > 5 else ""))
        print("  Installing missing dependencies ...")
        req = bundled_path("requirements.txt")
        _run([py, "-m", "pip", "install", "-r", req,
              "--no-warn-script-location", "--no-cache-dir"])
    elif missing == ["ALL"]:
        print("  Installing all dependencies (could not check) ...")
        req = bundled_path("requirements.txt")
        _run([py, "-m", "pip", "install", "-r", req,
              "--no-warn-script-location", "--no-cache-dir"])
    else:
        print("  All dependencies already installed ✓")

    # ── 3. Check & install Chromium ──
    print("\n  Checking Chromium browser ...")
    if _check_chromium(py):
        print("  Chromium already installed ✓")
    else:
        print("  Installing Chromium (first time only) ...")
        _run([py, "-m", "playwright", "install", "chromium"])

    # ── 4. Extract app files ──
    _extract_app_files()

    # ── 5. Mark done ──
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
    adir = app_dir()
    for name in APP_FILES:
        src = bundled_path(name)
        dst = os.path.join(adir, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)


# ── Launch ──────────────────────────────────────────────────────────────────

def launch():
    py, _ = _get_or_find_python()
    script = os.path.join(app_dir(), "nfshd.py")

    if not os.path.isfile(script):
        print("  ERROR: nfshd.py not found. Delete .faselhd_app/ and re-run.")
        _pause()
        sys.exit(1)

    os.chdir(app_dir())
    sys.exit(subprocess.run([py, script]).returncode)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
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
            print("  Fix: delete .faselhd_env/ and .faselhd_app/ then re-run.")
            _pause()
            sys.exit(1)
    else:
        if _needs_reextract():
            print("  Updating app files ...")
            _extract_app_files()
            exe_hash = _file_hash(sys.executable if getattr(sys, "frozen", False) else __file__)
            with open(version_marker(), "w") as f:
                f.write(exe_hash)

    launch()


if __name__ == "__main__":
    main()
