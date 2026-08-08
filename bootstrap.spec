# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for FaselHD Bootstrap EXE (~1-2 MB).

The bootstrap bundles ONLY:
  - bootstrap.py  (stdlib-only installer/launcher)
  - nfshd.py     (the real app — runs under embedded Python, NOT frozen)
  - mini_player.py
  - requirements.txt
  - src/icon.ico

On first run the bootstrap downloads Python 3.12 + deps + Chromium.
Subsequent runs launch instantly.

Build:  pyinstaller bootstrap.spec --noconfirm
Clean:  rmdir /s /q build dist
"""

import os

block_cipher = None

PROJECT_DIR = os.path.abspath(SPECPATH)
ICON_PATH = os.path.join(PROJECT_DIR, 'src', 'icon.ico')

if not os.path.isfile(ICON_PATH):
    print("[WARN] src/icon.ico not found — building without icon.")
    ICON_PATH = None

a = Analysis(
    [os.path.join(PROJECT_DIR, 'bootstrap.py')],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=[
        # Bundled as data — extracted at runtime, NOT compiled by PyInstaller
        (os.path.join(PROJECT_DIR, 'nfshd.py'),        '.'),
        (os.path.join(PROJECT_DIR, 'mini_player.py'),  '.'),
        (os.path.join(PROJECT_DIR, 'requirements.txt'), '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude EVERYTHING non-stdlib — bootstrap only uses:
        #   os, sys, zipfile, subprocess, urllib, shutil, hashlib
        'playwright', 'rich', 'requests', 'bs4', 'scrapling',
        'curl_cffi', 'imageio', 'imageio_ffmpeg', 'lxml',
        'greenlet', 'pyee', 'browserforge', 'apify_fingerprint_datapoints',
        'numpy', 'pandas', 'matplotlib', 'PIL', 'scipy',
        'IPython', 'jupyter', 'notebook',
        'tkinter', 'pyqt5', 'pyside6', 'PySide6', 'PyQt6',
        'unittest', 'pydoc', 'distutils', 'setuptools', 'pip',
        'test', 'tests',
        'm3u8', 'm3u8downloader', 'pyperclip',
        'certifi', 'idna', 'urllib3', 'charset_normalizer',
        'asyncio', 'logging', 'json', 'hashlib',
        'ctypes', 'email', 'html', 'http', 'xml',
        'sqlite3', 'ssl', 'multiprocessing', 'concurrent',
        'cryptography', 'nacl', 'h2', 'hpack', 'hyperframe',
        'click',
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if ICON_PATH else None,
)
