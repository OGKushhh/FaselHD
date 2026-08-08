# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for FaselHD (nfshd.exe)
Bundles nfshd.py + mini_player.py into a single executable with icon.

Build:  pyinstaller nfshd.spec --noconfirm
Clean:  rmdir /s /q build dist
"""

import os
import sys
import glob

block_cipher = None

# ── Paths ──
PROJECT_DIR = os.path.abspath(SPECPATH)
SRC_DIR = os.path.join(PROJECT_DIR, 'src')
ICON_PATH = os.path.join(SRC_DIR, 'icon.ico')

if not os.path.isfile(ICON_PATH):
    print(f"[WARNING] Icon not found at {ICON_PATH}")
    print("  Build will proceed without icon. Add src/icon.ico to fix this.")
    ICON_PATH = None

# ── Bundle Playwright Chromium browser files ──
# Find where Playwright installed Chromium on this machine
# Typically: %LOCALAPPDATA%\ms-playwright\chromium-xxxx\chrome-win\
playwright_browser_datas = []
pw_browsers_env = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '')
if sys.platform == 'win32':
    default_pw_path = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'ms-playwright')
else:
    default_pw_path = os.path.join(os.path.expanduser('~'), '.cache', 'ms-playwright')

pw_path = pw_browsers_env if pw_browsers_env else default_pw_path

if os.path.isdir(pw_path):
    for entry in os.listdir(pw_path):
        chromium_dir = os.path.join(pw_path, entry)
        if entry.startswith('chromium') and os.path.isdir(chromium_dir):
            # Found Chromium installation — bundle the chrome-win/ folder
            for subdir in os.listdir(chromium_dir):
                src = os.path.join(chromium_dir, subdir)
                if os.path.isdir(src):
                    # Bundle as: _playwright_browsers/chromium-xxxx/chrome-win/
                    dest = os.path.join('_playwright_browsers', entry, subdir)
                    playwright_browser_datas.append((src, dest))
                    print(f"  Bundling Playwright browser: {src} -> {dest}")
            break  # Only need the first (latest) chromium version

if not playwright_browser_datas:
    print("[WARNING] No Playwright Chromium found at", pw_path)
    print("  Chromium will be auto-installed on first run.")
    print("  To pre-bundle: run 'playwright install chromium' before building.")

# ── Data files to bundle ──
datas = [
    (os.path.join(PROJECT_DIR, 'mini_player.py'), '.'),
] + playwright_browser_datas

# ── Analysis ──
a = Analysis(
    [os.path.join(PROJECT_DIR, 'nfshd.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # ── Playwright core ──
        'playwright',
        'playwright.async_api',
        'playwright.sync_api',
        'playwright._impl',
        'playwright._impl._api_types',
        'playwright._impl._browser',
        'playwright._impl._browser_type',
        'playwright._impl._connection',
        'playwright._impl._driver',
        'playwright._impl._element_handle',
        'playwright._impl._errors',
        'playwright._impl._frame',
        'playwright._impl._helper',
        'playwright._impl._network',
        'playwright._impl._page',
        'playwright._impl._playwright',
        'playwright._impl._transport',
        'playwright._impl._server',
        'playwright._impl._cli',
        'playwright._impl._cli.main',
        'playwright.cli',
        'playwright.cli.main',
        # ── greenlet (Playwright dependency) ──
        'greenlet',
        'greenlet._greenlet',
        # ── pyee (Playwright event emitter) ──
        'pyee',
        'pyee.base',
        'pyee.cli',
        # ── Rich internals ──
        'rich.progress',
        'rich.console',
        'rich.table',
        'rich.panel',
        'rich.text',
        'rich.style',
        'rich.theme',
        'rich.segment',
        'rich.emoji',
        'rich.json',
        'rich._emoji_codes',
        'rich._log_render',
        'rich._wrap',
        'rich._ratio',
        'rich._pick',
        'rich._cells',
        # ── BeautifulSoup / lxml ──
        'bs4',
        'bs4.element',
        'bs4.builder',
        'bs4.builder._lxml',
        'lxml',
        'lxml._elementpath',
        'lxml.etree',
        'lxml.html',
        # ── requests + friends ──
        'certifi',
        'idna',
        'urllib3',
        'charset_normalizer',
        'requests',
        'requests.adapters',
        'requests.cookies',
        'requests.models',
        # ── scrapling (used in nfshd.py) ──
        'scrapling',
        'scrapling.fetcher',
        'scrapling.parser',
        'scrapling.engine',
        # ── curl_cffi ──
        'curl_cffi',
        'curl_cffi.requests',
        'curl_cffi.const',
        # ── imageio-ffmpeg ──
        'imageio_ffmpeg',
        # ── asyncio internals ──
        'asyncio',
        'asyncio.events',
        'asyncio.base_events',
        'asyncio.futures',
        'asyncio.tasks',
        # ── ctypes for Windows console ──
        'ctypes',
        'ctypes.wintypes',
        # ── m3u8 handling ──
        'm3u8',
        'm3u8downloader',
        # ── pyperclip ──
        'pyperclip',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'PIL', 'scipy',
        'IPython', 'jupyter', 'notebook',
        'unittest', 'pydoc', 'distutils',
        'setuptools', 'pip',
        'test', 'tests',
        'pyqt5', 'pyside6', 'PySide6', 'PyQt6',
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='nfshd',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # CLI app — keep console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if ICON_PATH else None,
)
