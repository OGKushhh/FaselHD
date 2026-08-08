# -*- coding: utf-8 -*-
# Author: Abdulrahman Mohammed (De3vil)
# Don't touch my code, it's art 
# +=============================
import os
import sys
import hashlib

# Fix #2: Force UTF-8 at the OS level BEFORE any imports
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PW_DEBUG"] = ""  # silence Playwright debug output
    try:
        import ctypes
        from ctypes import wintypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)

        # ── Set console font to one that supports Arabic/Unicode ──
        # Default "Consolas" lacks Arabic glyphs → question marks.
        # "Segoe UI" and "Arial" have full Unicode including Arabic.
        # Uses SetCurrentConsoleFontEx (Windows 10+).
        try:
            class _COORD(ctypes.Structure):
                _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]

            class _FONT_INFOEX(ctypes.Structure):
                _fields_ = [
                    ('cbSize', wintypes.ULONG),
                    ('nFont', wintypes.DWORD),
                    ('dwFontSize', _COORD),
                    ('FontFamily', wintypes.DWORD),
                    ('FontWeight', wintypes.DWORD),
                    ('FaceName', wintypes.WCHAR * 32),
                ]

            font_info = _FONT_INFOEX()
            font_info.cbSize = ctypes.sizeof(_FONT_INFOEX)
            font_info.dwFontSize = _COORD(0, 20)  # Default size
            font_info.FontFamily = 0x36  # TRUETYPE_FONT
            font_info.FontWeight = 400  # Normal
            # Try fonts with Arabic support in priority order
            _set_font = ctypes.windll.kernel32.SetCurrentConsoleFontEx
            for font_name in ["Consolas", "Cascadia Mono", "Segoe UI", "Arial"]:
                font_info.FaceName = font_name
                out_handle = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                result = _set_font(out_handle, False, ctypes.byref(font_info))
                if result:
                    break
        except Exception:
            pass  # Font setting failed — not critical, continue with default

        # Save original console input mode BEFORE Playwright touches it.
        # Chromium corrupts stdin handle mode on exit — we restore it after each fetch.
        _stdin_handle = ctypes.windll.kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        _original_console_mode = wintypes.DWORD(0)
        ctypes.windll.kernel32.GetConsoleMode(_stdin_handle, ctypes.byref(_original_console_mode))
    except Exception:
        _original_console_mode = None


def _restore_console_input():
    """Restore Windows console input mode AND codepage after Playwright/Chromium corrupts it.
    This fixes input() / console.input() hanging, ignoring keystrokes, and UTF-8 rendering."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # Restore input mode
        stdin_handle = ctypes.windll.kernel32.GetStdHandle(-10)
        if stdin_handle != -1 and stdin_handle is not None:
            if _original_console_mode is not None and _original_console_mode.value != 0:
                ctypes.windll.kernel32.SetConsoleMode(stdin_handle, _original_console_mode.value)
            else:
                ctypes.windll.kernel32.SetConsoleMode(stdin_handle, 0x0001 | 0x0002 | 0x0004 | 0x0080)
        # Re-enforce UTF-8 codepage (Playwright may reset it)
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass

import subprocess
import requests
import re
import json
import time
import asyncio
import logging
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeRemainingColumn, ProgressColumn
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
if hasattr(sys, '_MEIPASS'):
    os.environ["PLAYWRIGHT_CLI_EXECUTABLE"] = os.path.join(sys._MEIPASS, "playwright.exe")
from playwright.async_api import async_playwright

console = Console(force_terminal=True, legacy_windows=False)

# Reconfigure Python's stdout/stderr to UTF-8 AFTER Console creation.
# os.environ["PYTHONUTF8"]=1 inside the script doesn't enable UTF-8 mode
# (needs -X utf8 before Python starts). This reconfigure is the real fix.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ===================== Fix: Monkey-patch Console.input() to survive Playwright =====================
# Playwright/Chromium corrupts the console input buffer on Windows, making input()
# and console.input() hang or ignore keystrokes. SetConsoleMode alone isn't enough.
# Solution: use msvcrt.getwch() which reads directly from the hardware console buffer,
# completely bypassing whatever Playwright broke. Works with Arabic text too (getwch = Unicode).
if sys.platform == "win32":
    _original_rich_input = Console.input

    def _surviving_input(self, prompt="", *, password=False, stream=None):
        """Windows input that works even after Playwright destroys the console buffer.
        Uses msvcrt.getwch() to read character-by-character from the hardware console.
        All character echoing uses self.file.write() (raw stdout) to avoid Rich
        swallowing escape sequences like \\b for backspace."""
        self.print(prompt, end="")
        self.file.flush()
        try:
            import msvcrt
            chars = []
            while True:
                ch = msvcrt.getwch()
                if ch in ('\r', '\n'):
                    self.file.write('\n')
                    self.file.flush()
                    break
                elif ch == '\x03':  # Ctrl+C
                    self.file.write('\n')
                    self.file.flush()
                    raise KeyboardInterrupt
                elif ch in ('\x08', '\x7f'):  # Backspace or DEL
                    if chars:
                        chars.pop()
                        # Raw stdout: move cursor back, overwrite with space, move back again
                        self.file.write('\b \b')
                        self.file.flush()
                    continue
                elif ord(ch) == 0 or ord(ch) == 0xE0:
                    # Extended key (arrow keys, F-keys, etc.) — discard 2nd byte
                    try:
                        msvcrt.getwch()
                    except Exception:
                        pass
                    continue
                else:
                    chars.append(ch)
                    # Raw stdout echo — bypass Rich's markup parser
                    self.file.write(ch)
                    self.file.flush()
            return ''.join(chars)
        except Exception:
            # Last resort: try the original Rich input
            return _original_rich_input(self, prompt, password=password, stream=stream)

    Console.input = _surviving_input


# ===================== Suppress noisy scrapling/Playwright logs =====================
# Only show CF milestone messages, suppress everything else.
_cf_print_handler = logging.StreamHandler(sys.stderr)
_cf_print_handler.setLevel(logging.INFO)
_cf_print_handler.setFormatter(logging.Formatter("[%(message)s]"))

class _CFLogFilter(logging.Filter):
    """Only pass CF milestone messages; suppress wait spam and protocol noise."""
    def filter(self, record):
        if record.levelno >= logging.WARNING:
            return True
        msg = record.getMessage()
        if "Waiting for Cloudflare" in msg or "wait page to disappear" in msg:
            return False
        keep = ["captcha is solved", "captcha solved", "turnstile", "Fetched", "solved",
                "challenge", "cf-", "Detected", "bypassed", "success"]
        return any(k.lower() in msg.lower() for k in keep)

_cf_print_handler.addFilter(_CFLogFilter())
for _name in ["scrapling", "playwright", "asyncio", "urllib3", "httpcore", "httpx"]:
    _lg = logging.getLogger(_name)
    _lg.handlers = [_cf_print_handler]
    _lg.propagate = False

# ===================== Stealth Fetching: Scrapling (primary) + curl_cffi (fallback) =====================
try:
    from scrapling.engines._browsers._stealth import AsyncStealthySession
    SCRAPLING_AVAILABLE = True
except ImportError:
    SCRAPLING_AVAILABLE = False

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

MAX_RETRIES = 3
BACKOFF_FACTOR = 2
IMPERSONATIONS = ["chrome", "chrome110", "chrome124", "edge101", "safari15_5"]

# ===================== Persistent AsyncStealthySession (CF solved once, browser reused) =====================
# Key insight: CF cookies are TLS-fingerprint-bound — can't transfer to curl_cffi.
# Instead, keep ONE AsyncStealthySession alive. Browser stays open, CF session persists.
# First fetch solves CF (slow), subsequent fetches just navigate in same browser (fast).
_cf_session = None  # Persistent AsyncStealthySession instance


async def _get_cf_session():
    """Get or create the persistent AsyncStealthySession (browser stays open across calls)."""
    global _cf_session
    if _cf_session is None and SCRAPLING_AVAILABLE:
        try:
            _cf_session = AsyncStealthySession(headless=True)
            await _cf_session.start()
        except Exception as e:
            console.print(f"[yellow]Failed to create persistent session: {e}[/yellow]")
            _cf_session = None
    return _cf_session


async def _close_cf_session():
    """Close the persistent session's browser (call on app exit)."""
    global _cf_session
    if _cf_session is not None:
        try:
            await _cf_session.close()
        except Exception:
            pass
        _cf_session = None


async def get_website_safe(url: str, max_retries: int = MAX_RETRIES):
    """Fetch a page using persistent AsyncStealthySession (reuses browser, CF solved once).
    Uses LAZY CF: always tries without CF detection first. Only solves CF if the
    response is empty, a challenge page, or the fetch throws a timeout.
    Falls back to curl_cffi if scrapling is unavailable.
    Returns a requests.Response-like object with .text and .status_code, or None."""

    def _is_good_response(html):
        """Check if HTML is actual content (not a CF challenge or empty page)."""
        return html and len(html) > 200 and \
               'challenge-platform' not in html.lower() and \
               'just a moment' not in html.lower()

    def _resp_to_html(resp):
        """Extract HTML string from a scrapling response object."""
        if not resp:
            return None
        body = getattr(resp, 'body', None)
        text = getattr(resp, 'text', '')
        return body.decode('utf-8') if isinstance(body, bytes) else text

    # --- Strategy 1: Persistent session (lazy CF — solve only when needed) ---
    session = await _get_cf_session()
    if session:
        try:
            # STEP 1: Always try WITHOUT CF solving first (fast path).
            # If browser already has CF cookies from a previous solve, this just works.
            try:
                resp = await session.fetch(
                    url,
                    block_ads=True,
                    solve_cloudflare=False,
                    wait_selector=".blockMovie, .postDiv, body",
                    retries=1, retry_delay=2,
                    timeout=30000
                )
            finally:
                _restore_console_input()

            html = _resp_to_html(resp)
            status = getattr(resp, 'status', '??') if resp else '??'

            if status == 200 and _is_good_response(html):
                return _make_fake_response(html.encode('utf-8'))

            # STEP 2: Response is bad (CF challenge, empty, or timeout).
            # Now solve CF — browser stays open, only done once.
            console.print("[cyan]⏳ Bypassing Cloudflare... please wait.[/cyan]")
            try:
                resp = await session.fetch(
                    url,
                    block_ads=True,
                    solve_cloudflare=True,
                    wait_selector=".blockMovie, .postDiv, body",
                    retries=2, retry_delay=3,
                    timeout=45000
                )
            finally:
                _restore_console_input()

            html = _resp_to_html(resp)
            status = getattr(resp, 'status', '??') if resp else '??'

            if status == 200 and _is_good_response(html):
                console.print("[green]✓ Cloudflare bypassed.[/green]")
                return _make_fake_response(html.encode('utf-8'))

        except Exception as e:
            err_msg = str(e)
            console.print(f"[yellow]Scrapling error: {e}[/yellow]")
            # Timeout? Try once more with CF solving + longer timeout
            if 'timeout' in err_msg.lower() and session is not None:
                console.print("[dim]Retrying with CF solving + longer timeout...[/dim]")
                try:
                    console.print("[cyan]⏳ Bypassing Cloudflare... please wait.[/cyan]")
                    retry_resp = await session.fetch(
                        url,
                        block_ads=True,
                        solve_cloudflare=True,
                        wait_selector=".blockMovie, .postDiv, body",
                        retries=1, retry_delay=5,
                        timeout=60000
                    )
                    _restore_console_input()
                    retry_html = _resp_to_html(retry_resp)
                    retry_status = getattr(retry_resp, 'status', '??') if retry_resp else '??'
                    if retry_status == 200 and _is_good_response(retry_html):
                        console.print("[green]✓ Cloudflare bypassed.[/green]")
                        return _make_fake_response(retry_html.encode('utf-8'))
                except Exception as retry_e:
                    console.print(f"[yellow]Retry also failed: {retry_e}[/yellow]")
                    _restore_console_input()

    # --- Strategy 2: Classmethod async_fetch (new browser each time, last resort) ---
    if SCRAPLING_AVAILABLE:
        try:
            from scrapling.fetchers import StealthyFetcher
            console.print("[cyan]⏳ Bypassing Cloudflare (new browser)...[/cyan]")
            try:
                resp = await StealthyFetcher.async_fetch(
                    url,
                    disable_resources=True,
                    solve_cloudflare=True,
                    block_ads=True,
                    wait_selector=".blockMovie, .postDiv, body",
                    retries=2,
                    retry_delay=3,
                    timeout=30000
                )
            finally:
                _restore_console_input()
            if resp and resp.status == 200:
                html = resp.body.decode('utf-8') if hasattr(resp, 'body') else resp.text
                if html:
                    console.print("[green]✓ Cloudflare bypassed.[/green]")
                    return _make_fake_response(html.encode('utf-8'))
        except Exception as e:
            console.print(f"[yellow]Scrapling classmethod error: {e}[/yellow]")
            _restore_console_input()

    # --- Strategy 3: Bare curl_cffi (no CF bypass, may fail on protected pages) ---
    if CURL_CFFI_AVAILABLE:
        for attempt in range(max_retries):
            imp = IMPERSONATIONS[attempt % len(IMPERSONATIONS)]
            try:
                r = await asyncio.to_thread(
                    curl_requests.get, url, impersonate=imp, timeout=30
                )
                if r.status_code == 200:
                    return _make_fake_response(r.content)
            except Exception as e:
                console.print(f"[yellow]curl_cffi error: {e}[/yellow]")
            if attempt < max_retries - 1:
                await asyncio.sleep(BACKOFF_FACTOR ** attempt)

    console.print(f"[red]Failed to fetch {url}[/red]")
    return None


def _make_fake_response(content_bytes):
    """Create a requests.Response-like object from raw bytes."""
    fake = requests.Response()
    fake.status_code = 200
    fake._content = content_bytes
    return fake


def stream_to_player(m3u8_url, player_path=None):
    """Open an m3u8 stream — uses Windows 'Open With' dialog so the user
    can pick any installed media player (VLC, PotPlayer, MPV, etc.)."""
    console.print(f"\n[cyan]Stream URL: [dim]{m3u8_url}[/dim][/cyan]")
    console.print("[green]Opening app picker — choose your media player...[/green]")
    try:
        if sys.platform == "win32":
            import ctypes
            import tempfile

            # Write a proper .m3u8 playlist file
            tmp = tempfile.NamedTemporaryFile(suffix=".m3u8", delete=False, mode='w', encoding='utf-8')
            tmp.write("#EXTM3U\n")
            tmp.write(f"#EXTINF:-1,Stream\n")
            tmp.write(m3u8_url)
            tmp_path = tmp.name
            tmp.close()

            # Use ShellExecuteW with "openas" verb — this is the reliable way to
            # trigger the Windows "Open With" dialog (works even for .m3u8)
            # HWND = 0 (desktop), verb = "openas", file = tmp_path, params = None
            result = ctypes.windll.shell32.ShellExecuteW(
                0, "openas", tmp_path, None, None, 1  # SW_SHOWNORMAL
            )
            # ShellExecuteW returns >32 on success
            if result <= 32:
                console.print(f"[yellow]ShellExecute failed (code {result}), trying alternative...[/yellow]")
                # Fallback: use os.startfile which also triggers Open With for unknown extensions
                os.startfile(tmp_path)

            # Clean up temp file after a delay (player needs time to read it)
            def _cleanup():
                try:
                    import time
                    time.sleep(10)
                    os.unlink(tmp_path)
                except Exception:
                    pass
            import threading
            threading.Thread(target=_cleanup, daemon=True).start()
            return True
        else:
            os.startfile(m3u8_url)
            return True
    except Exception as e:
        console.print(f"[red]Failed to open app picker: {e}[/red]")
        return False


def launch_mini_player(m3u8_url, title=""):
    """Launch the built-in FaselHD Mini Player. Pass title for window caption."""
    if hasattr(sys, '_MEIPASS'):
        # Frozen EXE: extract mini_player.py from bundle
        mini_player_script = os.path.join(sys._MEIPASS, "mini_player.py")
    else:
        # Normal Python: find next to nfshd.py
        mini_player_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mini_player.py")

    if getattr(sys, 'frozen', False):
        # When frozen, sys.executable is nfshd.exe — not Python.
        # Try to find a system Python to run mini_player.py
        python_cmd = None
        for cmd in ['python', 'python3', 'py']:
            try:
                r = subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
                if r.returncode == 0:
                    python_cmd = cmd
                    break
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                continue

        if python_cmd:
            try:
                cmd = [python_cmd, mini_player_script, m3u8_url]
                if title:
                    cmd.append(title)
                subprocess.Popen(cmd)
                console.print("[green]Launching FaselHD Mini Player...[/green]")
                return True
            except Exception as e:
                console.print(f"[red]Could not launch Mini Player: {e}[/red]")

        # No Python found — fall back to opening URL in default player
        console.print("[yellow]Python not found — opening in system default player...[/yellow]")
        os.startfile(m3u8_url)
        return True
    else:
        # Normal Python environment
        try:
            cmd = [sys.executable, mini_player_script, m3u8_url]
            if title:
                cmd.append(title)
            subprocess.Popen(cmd)
            console.print("[green]Launching FaselHD Mini Player...[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Could not launch Mini Player: {e}[/red]")
            console.print("[yellow]Falling back to system default player...[/yellow]")
            os.startfile(m3u8_url)
            return True


# ===================== Setup: ffmpeg (auto-download on first run) + Chromium via Playwright =====================

_FFMPEG_VERSION = "7.1"
_FFMPEG_URL = f"https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essential.zip"
_FFMPEG_EXE_NAME = "ffmpeg.exe"

def _get_ffmpeg_dir():
    """Get the persistent ffmpeg cache directory (next to EXE in frozen mode)."""
    if getattr(sys, 'frozen', False):
        d = os.path.join(os.path.dirname(sys.executable), ".ffmpeg")
    else:
        d = os.path.join(os.path.expanduser("~"), ".faselhd_ffmpeg")
    os.makedirs(d, exist_ok=True)
    return d

def get_ffmpeg_path():
    """Find ffmpeg: bundled cache → imageio-ffmpeg → system PATH."""
    # 1. Check our own cache (downloaded on first run)
    cached = os.path.join(_get_ffmpeg_dir(), _FFMPEG_EXE_NAME)
    if os.path.isfile(cached):
        return cached
    # 2. Check imageio-ffmpeg package (normal Python only)
    try:
        import imageio_ffmpeg
        exe_path = imageio_ffmpeg.get_ffmpeg_exe()
        if exe_path and os.path.isfile(exe_path):
            return exe_path
    except Exception:
        pass
    # 3. Check system PATH
    try:
        result = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    return None

_ffmpeg_cached_path = None


def _download_ffmpeg():
    """Download ffmpeg.exe to the cache directory. Returns path or None."""
    import zipfile
    import io
    cache_dir = _get_ffmpeg_dir()
    target = os.path.join(cache_dir, _FFMPEG_EXE_NAME)

    console.print(f"[blue]Downloading ffmpeg (first time only)...[/blue]")
    try:
        resp = requests.get(_FFMPEG_URL, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get('content-length', 0))
        downloaded = 0
        chunk_size = 8192
        zip_bytes = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=chunk_size):
            zip_bytes.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded * 100 // total
                mb = downloaded / (1024 * 1024)
                print(f"\r  Downloading: {mb:.1f} MB ({pct}%)", end="", flush=True)
        print()  # newline after progress

        # Extract only ffmpeg.exe from the zip
        console.print("[blue]Extracting ffmpeg.exe...[/blue]")
        with zipfile.ZipFile(zip_bytes) as zf:
            for name in zf.namelist():
                if name.lower().endswith(_FFMPEG_EXE_NAME):
                    # Preserve folder structure — find the bin/ subfolder
                    source = zf.open(name)
                    with open(target, 'wb') as dest:
                        while True:
                            chunk = source.read(8192)
                            if not chunk:
                                break
                            dest.write(chunk)
                    break
        zip_bytes.close()

        if os.path.isfile(target):
            size_mb = os.path.getsize(target) / (1024 * 1024)
            console.print(f"[green]ffmpeg installed successfully ({size_mb:.1f} MB).[/green]")
            return target
        else:
            console.print("[red]ffmpeg.exe not found inside the archive.[/red]")
            return None
    except Exception as e:
        console.print(f"[red]Failed to download ffmpeg: {e}[/red]")
        return None


def ensure_ffmpeg():
    """Ensure ffmpeg is available. Auto-downloads on first run if needed.
    Returns path or None (cached after first call)."""
    global _ffmpeg_cached_path
    if _ffmpeg_cached_path is not None:
        return _ffmpeg_cached_path if _ffmpeg_cached_path else None

    ffmpeg_path = get_ffmpeg_path()
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        _ffmpeg_cached_path = ffmpeg_path
        return ffmpeg_path

    # Not found — try to auto-download
    downloaded = _download_ffmpeg()
    if downloaded:
        _ffmpeg_cached_path = downloaded
        return downloaded

    _ffmpeg_cached_path = False
    console.print("[yellow]ffmpeg not available. Downloads will use fallback method.[/yellow]")
    return None

def ensure_chromium():
    """Ensure Playwright's Chromium browser is installed.
    In frozen EXE, Chromium is auto-installed on first run next to the EXE."""
    # When frozen, use a persistent browsers dir next to the EXE
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        browsers_dir = os.path.join(exe_dir, ".playwright-browsers")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_dir
    # Check if Chromium is already installed
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True)
            browser.close()
            pw.stop()
            console.print("[green]Chromium is ready.[/green]")
            return
        except Exception:
            pw.stop()
    except Exception:
        pass
    # Not installed — install it
    console.print("[blue]Installing Chromium (first time only, this may take a minute)...[/blue]")
    try:
        if getattr(sys, 'frozen', False):
            # Frozen EXE: use playwright CLI module directly
            from playwright.cli.main import main as pw_cli_main
            old_argv = sys.argv
            sys.argv = ["playwright", "install", "chromium"]
            try:
                pw_cli_main()
            except SystemExit:
                pass
            sys.argv = old_argv
        else:
            # Normal Python: use pip module
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True
            )
        console.print("[green]Chromium installed successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to install Chromium: {e}[/red]")
        console.print("[yellow]The app will still work but video extraction may fail.[/yellow]")



banner = r"""
[red]███████ [yellow]███████ [cyan]██   ██ ██████  
[red]██      [yellow]██      [cyan]██   ██ ██   ██ 
[red]█████   [yellow]███████ [cyan]███████ ██   ██ 
[red]██       [yellow]    ██ [cyan]██   ██ ██   ██ 
[red]██      [yellow]███████ [cyan]██   ██ ██████                                 
               [white][[red]=>[/red]][/white] [yellow]Created by[red]:[/red][bold red]Abdulrahman Mohammed[/bold red][white]([cyan]De3vil[/cyan])[/white] [white][[red]<=[/red]][/white]
             \___________________________________________________/  
"""
console.print(banner)


# Ad domains to block (from working VideoExtractor)
BLOCKED_DOMAINS = [
    "s8ey.com", "wplmtckt.com", "reffpa.com", "1xlite-11151.pro", "pyppo.com",
    "googletagmanager.com", "doubleclick.net", "googleadservices.com",
    "google-analytics.com", "popads.net", "adsterra.com", "exponential.com",
    "outbrain.com", "taboola.com", "scorecardresearch.com", "madurird.com",
    "acscdn.com", "crumpetprankerstench.com", "propellerads.com",
    "clickadu.com", "adnxs.com", "ads.yahoo.com",
    "notix.io", "pushwoosh.com", "onesignal.com",
    "tmll7.com", "1xlite-24510.bar", "mahjong778jpx.site",
    "browsecoherentunrefined.com",
]

# Multiple play selectors to try inside player iframe
PLAY_SELECTORS = [
    ".jw-icon-display",
    ".jw-icon.jw-icon-display",
    ".jw-display-icon-container",
    "[class*='jw-icon'][class*='play']",
    ".jw-media video",
    "video",
    "[class*='play'][class*='btn']",
    "[class*='play'][class*='button']",
    "[class*='video-play']",
]

TEMP_PROFILE = os.path.join(os.path.expanduser("~"), ".faselhd_browser_profile")

class BrowserManager:
    """Manages Playwright browser context for m3u8 video extraction only.
    All page fetching (search, seasons, episodes) uses scrapling/curl_cffi instead."""
    def __init__(self):
        self.playwright = None
        self.context = None

    async def start(self):
        await asyncio.to_thread(ensure_chromium)
        self.playwright = await async_playwright().start()
        os.makedirs(TEMP_PROFILE, exist_ok=True)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=TEMP_PROFILE,
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--window-size=1280,720",
            ],
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            ignore_default_args=["--enable-automation"],
        )
        # Block ad domains
        async def block_ads(route, request):
            if any(d in request.url for d in BLOCKED_DOMAINS):
                await route.abort()
                return
            await route.continue_()
        await self.context.route("**/*", block_ads)
        console.print("[green]Browser ready for video extraction.[/green]")

    async def new_page(self):
        return await self.context.new_page()

    async def close_page(self, page):
        try:
            await page.close()
        except Exception:
            pass

    async def close(self):
        try:
            await self.context.close()
        except Exception:
            pass
        try:
            await self.playwright.stop()
        except Exception:
            pass

FASEL_BASE_URL = "https://www.fasel-hd.cam/"
CACHE_DIR = ".cache"
CACHE_TTL = 300  # 5 minutes TTL for search cache

# ── Category metadata from URL slugs ──
_CATEGORY_META = {
    "movies":            ("🎬", "Movies"),
    "tvshows":           ("📺", "TV Shows"),
    "asian-movies":      ("🎞️", "Asian Movies"),
    "asian-series":      ("📺", "Asian Series"),
    "dubbed-movies":     ("🗣️", "Dubbed"),
    "anime":             ("🎌", "Anime"),
    "anime-movies":      ("🎌", "Anime Movies"),
    "hindi":             ("🎬", "Hindi"),
    "movies_collections": ("🎥", "Collections"),
    "series":            ("📺", "Series"),
}


def _extract_category(url: str):
    """Extract category icon and label from a FaselHD URL.
    Returns (icon, label) tuple, e.g. ('🎬', 'Movies').
    Falls back to ('🎬', 'Movies') if unrecognized."""
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path.strip('/')
        # URL format: /category/slug/ or /category/slug
        parts = [p for p in path.split('/') if p and p != FASEL_BASE_URL.rstrip('/')]
        if parts:
            slug = parts[0].lower()
            if slug in _CATEGORY_META:
                return _CATEGORY_META[slug]
    except Exception:
        pass
    return ("🎬", "Movies")


def _cache_key(query: str) -> str:
    """Generate a filesystem-safe cache key from a search query."""
    h = hashlib.md5(query.strip().lower().encode('utf-8')).hexdigest()[:12]
    return os.path.join(CACHE_DIR, f"search_{h}.json")


def _load_search_cache(query: str):
    """Load cached search results if they exist and haven't expired. Returns list or None."""
    cache_path = _cache_key(query)
    if not os.path.isfile(cache_path):
        return None
    try:
        import time as _time
        mtime = os.path.getmtime(cache_path)
        if _time.time() - mtime > CACHE_TTL:
            return None  # Expired
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Each entry is [title, url]
        return [[t, u] for t, u in data]
    except Exception:
        return None


def _save_search_cache(query: str, results):
    """Save search results to cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = _cache_key(query)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


async def search(user_input):
    """
    Search using direct URL: https://www.fasel-hd.cam/?s=query
    Uses scrapling/curl_cffi (no Playwright) — bypasses Cloudflare natively.
    Results are cached for 5 minutes (CACHE_TTL) in .cache/search_<hash>.json.
    Returns list of [title, url] pairs.
    """
    # Check cache first
    cached = _load_search_cache(user_input)
    if cached is not None:
        console.print("[dim]Loaded from cache (expires in 5 min).[/dim]")
        return cached

    results = []
    try:
        search_URL = FASEL_BASE_URL.rstrip('/') + "/?s=" + requests.utils.quote(user_input.strip())
        resp = await get_website_safe(search_URL)
        if not resp:
            return results
        soup = BeautifulSoup(resp.text, "html.parser")
        items = (soup.select(".blockMovie") or
                 soup.select(".postDiv") or
                 soup.select(".col-xl-2.col-lg-2.col-md-3.col-sm-3") or
                 soup.select("article"))
        if not items:
            items = soup.select("a[href]")
        for idx, item in enumerate(items):
            link_tag = item if item.name == "a" else item.find("a")
            if not link_tag:
                continue
            title_elem = (item.select_one(".h5") or
                          item.select_one(".h1") or
                          item.select_one(".h4") or
                          item.select_one(".title") or
                          item.select_one(".entry-title"))
            title = title_elem.text.strip() if title_elem else link_tag.get("title", "").strip()
            if not title:
                title = link_tag.text.strip()
            href = link_tag.get("href", "")
            if not href or not title or len(title) < 2:
                continue
            if href in ("#", "/", FASEL_BASE_URL):
                continue
            results.append([title, href])
        # Deduplicate by href
        seen = set()
        unique = []
        for t, h in results:
            if h not in seen:
                seen.add(h)
                unique.append([t, h])
        _save_search_cache(user_input, unique)
        return unique
    except Exception as e:
        console.print(f"[red]Error during search: {e}[/red]")
        return results


async def extract_seasons(series_url):
    full_url = urljoin(FASEL_BASE_URL, series_url)
    seasons_links = []
    try:
        resp = await get_website_safe(full_url)
        if not resp:
            return seasons_links
        soup = BeautifulSoup(resp.text, "html.parser")
        season_divs = soup.select('#seasonList .seasonDiv')
        for season_div in season_divs:
            onclick = season_div.get('onclick')
            if not onclick:
                continue
            match = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
            if match:
                link = match.group(1)
                if link.startswith('?') or link.startswith('/'):
                    link = FASEL_BASE_URL.rstrip('/') + link
                seasons_links.append(link)
    except Exception as e:
        console.print(f"[red]Error extracting seasons: {e}[/red]")
    return seasons_links

async def extract_episodes(season_url):
    episode_links = []
    try:
        resp = await get_website_safe(season_url)
        if not resp:
            return episode_links
        soup = BeautifulSoup(resp.text, "html.parser")
        ep_all = soup.select_one('#epAll, .epAll')
        if ep_all:
            for a in ep_all.find_all('a', href=True):
                href = a['href'].strip()
                if href:
                    if href.startswith('/'):
                        href = FASEL_BASE_URL.rstrip('/') + href
                    episode_links.append(href)
        if not episode_links:
            # Fallback selectors
            for sel in ['.epDiv a', '.episode-item a', '.episodeDiv a']:
                items = soup.select(sel)
                for a in items:
                    href = a.get('href', '').strip()
                    if href:
                        if href.startswith('/'):
                            href = FASEL_BASE_URL.rstrip('/') + href
                        episode_links.append(href)
                if episode_links:
                    break
    except Exception as e:
        console.print(f"[red]Error extracting episodes: {e}[/red]")
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for link in episode_links:
        norm = link.rstrip('/').lower()
        if norm not in seen:
            seen.add(norm)
            unique.append(link)
    return unique

async def extract_movie_links(movie_url):
    """Check if a movie page has a player iframe. Returns [url] or []."""
    try:
        resp = await get_website_safe(movie_url)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        iframe = soup.find("iframe", attrs={"name": "player_iframe"})
        return [movie_url] if iframe else []
    except Exception as e:
        console.print(f"[red]Error extracting movie links: {e}[/red]")
        return []


# ===================== Trending / Popular movies from homepage =====================

FASEL_MAIN_URL = FASEL_BASE_URL.rstrip('/') + "/main"


async def fetch_trending():
    """Fetch trending/recent movies from the FaselHD main page (/main).
    Parses sections (latest movies, latest series, latest episodes, etc.).
    Returns list of (title, url) tuples, or empty list on failure."""
    try:
        resp = await get_website_safe(FASEL_MAIN_URL)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        trending = []
        seen_urls = set()

        # Each section has .blockHead > .h3 for title, followed by .blockMovie items
        items = soup.select("section#blockList .blockMovie")
        if not items:
            # Fallback: all .blockMovie on the page
            items = soup.select(".blockMovie")
        if not items:
            items = soup.select(".postDiv")
        if not items:
            items = soup.select("article")

        for item in items[:15]:  # Top 15
            link_tag = item.find("a")
            if not link_tag:
                continue
            title_elem = item.select_one(".h5")
            title = title_elem.text.strip() if title_elem else link_tag.get("title", "").strip()
            if not title:
                title = link_tag.text.strip()
            href = link_tag.get("href", "")
            if not href or not title or len(title) < 2:
                continue
            # Skip category/nav links
            if href in ("#", "/", FASEL_BASE_URL, FASEL_MAIN_URL):
                continue
            # Skip non-content pages
            if any(skip in href for skip in ['/most_recent', '/all-movies', '/series', '/movies_collections', '/asian-series']):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)
            trending.append((title, href))
        return trending
    except Exception:
        return []


# ===================== M3U8 Quality Parser =====================

QUALITY_TIERS = [2160, 1440, 1080, 720, 480, 360, 240]


def _snap_to_tier(height: int) -> int:
    """Snap a resolution height to the nearest standard tier."""
    closest = QUALITY_TIERS[0]
    min_diff = abs(height - closest)
    for tier in QUALITY_TIERS:
        diff = abs(height - tier)
        if diff < min_diff:
            min_diff = diff
            closest = tier
    return closest


def _resolve_url(base: str, child: str) -> str:
    """Resolve a potentially relative child URL against a base URL."""
    if child.startswith('http'):
        return child
    base_dir = base[:base.rfind('/') + 1]
    return base_dir + child


async def parse_m3u8_qualities(m3u8_url: str):
    """Fetch a master m3u8 playlist and parse available quality levels.
    Returns dict: { '1080': {'resolution': 1080, 'uri': '...'}, '720': {...}, ... }
    or None if the playlist is not a master (single quality) or on error."""
    try:
        resp = await asyncio.to_thread(
            requests.get, m3u8_url,
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=10
        )
        text = resp.text
    except Exception:
        return None

    if not text or '#EXT-X-STREAM-INF' not in text:
        return None  # Not a master playlist — single quality

    qualities = {}
    lines = text.split('\n')

    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith('#EXT-X-STREAM-INF'):
            continue

        # Find the next non-comment, non-empty line (the child URI)
        child_uri = ''
        for j in range(i + 1, len(lines)):
            nxt = lines[j].strip()
            if nxt and not nxt.startswith('#'):
                child_uri = nxt
                break

        # Extract resolution
        height = 0
        res_match = re.search(r'RESOLUTION=(\d+)x(\d+)', line, re.IGNORECASE)
        if res_match:
            height = _snap_to_tier(int(res_match.group(2)))
        else:
            # Fallback: estimate from bandwidth
            bw_match = re.search(r'BANDWIDTH=(\d+)', line, re.IGNORECASE)
            if bw_match:
                bw = int(bw_match.group(1))
                if bw >= 6_000_000:
                    height = 1080
                elif bw >= 3_000_000:
                    height = 720
                elif bw >= 1_000_000:
                    height = 480
                else:
                    height = 360

        if height and str(height) not in qualities:
            qualities[str(height)] = {
                'resolution': height,
                'uri': _resolve_url(m3u8_url, child_uri) if child_uri else None
            }

    return qualities if qualities else None


# ===================== Refactored: Extract m3u8 URL (reusable) =====================

async def extract_m3u8_url(browser_manager, page_url, quality=None, video_type="episode"):
    """
    Extract the m3u8 streaming URL from a video page.
    Uses network interception + anti-bot detection (synced with VideoExtractor.tsx).

    Now includes REAL quality detection:
    - Captures the master m3u8 URL via network interception
    - Fetches and parses the master playlist to discover actual resolutions
    - Returns child URIs for each quality level (for downloads)
    - Falls back to URL-based guessing if master parsing fails

    Returns (m3u8_url, quality_map, best_quality) or (None, None, None) on failure.
      - m3u8_url: the master playlist URL (or single-quality URL)
      - quality_map: { '1080': {'resolution': 1080, 'uri': 'child_url'}, ... }
                     or { 'auto': {'resolution': 0, 'uri': None} } for single quality
      - best_quality: string like '1080', '720', etc.
    """
    page = await browser_manager.new_page()
    captured_urls = []

    async def on_request(request):
        if '.m3u8' in request.url:
            captured_urls.append(request.url)

    try:
        page.on("request", on_request)
        await page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(2)

        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2);")
        await asyncio.sleep(1)

        # Step 1: Extract server tokens from .tabs-ul (same as VideoExtractor CLICK_JS)
        server_tokens = await page.evaluate("""() => {
            var serverTabs = document.querySelectorAll('.tabs-ul li');
            var tokens = [];
            serverTabs.forEach(function(li) {
                var oc = li.getAttribute('onclick') || '';
                var m = oc.match(/player_iframe\\.location\\.href\\s*=\\s*['"]([^'"]+)['"]/);
                if (m && m[1]) tokens.push(m[1]);
            });
            return tokens;
        }""")

        # Step 2: Locate player iframe (name > id > first iframe fallback)
        iframe = page.frame(name="player_iframe")
        iframe_elem = None
        if not iframe:
            iframe_elem = await page.query_selector("iframe[name='player_iframe']")
            if not iframe_elem:
                iframe_elem = await page.query_selector("iframe#player_iframe")
            if not iframe_elem:
                iframe_elem = await page.query_selector("iframe")
            if iframe_elem:
                iframe = await iframe_elem.content_frame()

        # Step 3: Navigate iframe to video_player URL if needed
        if iframe and iframe_elem:
            src_attr = (await iframe_elem.get_attribute("data-src") or
                        await iframe_elem.get_attribute("src") or "")
            if "video_player" in src_attr:
                try:
                    await iframe.goto(src_attr, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

        # Step 4: Click play inside iframe with multiple selector attempts
        if iframe:
            try:
                await iframe.wait_for_selector("body", timeout=10000)
                for attempt in range(7):
                    if captured_urls:
                        break
                    for sel in PLAY_SELECTORS:
                        try:
                            await iframe.click(sel, force=True, timeout=2000)
                            break
                        except Exception:
                            continue
                    await asyncio.sleep(1.5)
            except Exception:
                pass
        else:
            # No iframe — click directly on main page
            for attempt in range(5):
                if captured_urls:
                    break
                for sel in [".jw-icon-display", "video"]:
                    try:
                        await page.click(sel, force=True, timeout=2000)
                        break
                    except Exception:
                        continue
                await asyncio.sleep(1.5)

        # Step 5: Wait for delayed m3u8 capture (up to 15 seconds)
        for _ in range(30):
            if captured_urls:
                break
            await asyncio.sleep(0.5)

        page.remove_listener("request", on_request)

        if not captured_urls:
            console.print(f"[red]No m3u8 stream found for {page_url}[/red]")
            return None, None, None

        # Prefer master.m3u8, fall back to first captured
        m3u8_url = None
        for u in captured_urls:
            if 'master.m3u8' in u:
                m3u8_url = u
                break
        if not m3u8_url:
            m3u8_url = captured_urls[0]

        console.print(f"[dim]Captured m3u8: {m3u8_url}[/dim]")

        # ── Real quality detection: parse master playlist ──
        quality_map = None
        best_quality = quality or '1080'

        parsed = await parse_m3u8_qualities(m3u8_url)
        if parsed:
            quality_map = parsed
            # Best available = highest resolution
            available_sorted = sorted(parsed.keys(), key=lambda q: int(q), reverse=True)
            best_quality = available_sorted[0]
            console.print(f"[green]Detected qualities: {', '.join(f'{q}p' for q in available_sorted)}[/green]")
        else:
            # Fallback: guess from URL string (old behavior)
            console.print("[dim]Master playlist parse failed — guessing quality from URL.[/dim]")
            guessed = '1080'
            for q in ['1080', '720', '360']:
                if q in m3u8_url:
                    guessed = q
                    break
            quality_map = {guessed: {'resolution': int(guessed), 'uri': None}}
            best_quality = guessed

        # If user requested a specific quality, validate it exists
        if quality and quality not in quality_map:
            # Find closest lower quality
            available_sorted = sorted(quality_map.keys(), key=lambda q: int(q), reverse=True)
            for q in available_sorted:
                if int(q) <= int(quality):
                    quality = q
                    break
            else:
                quality = available_sorted[-1]  # Lowest available

        return m3u8_url, quality_map, best_quality

    except Exception as e:
        console.print(f"[red]Error extracting m3u8 URL: {e}[/red]")
        return None, None, None
    finally:
        await browser_manager.close_page(page)
        # Restore console input after Playwright page interactions (clicks, navigations)
        _restore_console_input()


class TightBarColumn(ProgressColumn):
    def __init__(self, width: int = 40):
        self.width = width
        super().__init__()
    def render(self, task):
        complete = int(task.percentage / 100 * self.width)
        incomplete = self.width - complete
        text = Text()
        text.append("━" * complete, style="magenta")
        text.append("━" * incomplete, style="grey37")
        return text


# ===================== Download (uses extract_m3u8_url) =====================

MAX_DOWNLOAD_RETRIES = 3
MAX_CONCURRENT_DOWNLOADS = 3  # Semaphore limit for parallel episode downloads


def _parse_episode_input(raw_input: str, max_episodes: int):
    """Parse episode input string into a sorted list of 0-based indices.
    Supports: single '1', comma-sep '1,3,5', ranges '1-5', mixed '1,3,5-8', 'all'.
    Returns list of valid 0-based indices, or None on parse error."""
    raw = raw_input.strip()
    if raw.lower() == 'all':
        return list(range(max_episodes))

    indices = set()
    parts = raw.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            # Range: 1-5
            segs = part.split('-')
            if len(segs) != 2:
                return None
            try:
                start = int(segs[0].strip())
                end = int(segs[1].strip())
            except ValueError:
                return None
            if start < 1 or end < 1 or start > end:
                return None
            for n in range(start, end + 1):
                indices.add(n - 1)
        else:
            try:
                n = int(part)
                if n < 1:
                    return None
                indices.add(n - 1)
            except ValueError:
                return None

    # Validate all within range and return sorted
    result = sorted(idx for idx in indices if 0 <= idx < max_episodes)
    invalid = sorted(idx for idx in indices if idx < 0 or idx >= max_episodes)
    if invalid:
        # Return special value to signal some were out of range
        return (result, invalid)
    return result


def _format_episode_list(indices, max_episodes):
    """Format a list of 0-based indices into a compact human-readable string.
    E.g. [0,1,2,4,5,7] -> 'E01-E03, E04-E05, E07'"""
    if not indices:
        return '(none)'
    nums = [i + 1 for i in indices]  # Convert to 1-based
    ranges = []
    start = nums[0]
    end = nums[0]
    for n in nums[1:]:
        if n == end + 1:
            end = n
        else:
            if start == end:
                ranges.append(f'E{start:02d}')
            else:
                ranges.append(f'E{start:02d}-E{end:02d}')
            start = n
            end = n
    if start == end:
        ranges.append(f'E{start:02d}')
    else:
        ranges.append(f'E{start:02d}-E{end:02d}')
    return ', '.join(ranges)


class FaselHDApp:
    """FaselHD CLI application — search, browse, stream movies and series."""

    def __init__(self):
        self.current_series = None
        self.is_movie = False
        self._exiting = False
        self._browser_manager = None
        self._stored_episodes = []
        self._season_number = 0
        self._episode_indices = []
        self._probed_m3u8 = None      # Cached: (master_url, quality_map, best_quality)
        self._probed_url = None       # Which URL was probed (movie url or first ep url)
        self._ep_probes = {}         # Pre-probed cache: {ep_url: (master, qmap, best)}

    async def _get_browser(self):
        """Lazy-start BrowserManager only when m3u8 extraction is needed."""
        if self._browser_manager is None:
            self._browser_manager = BrowserManager()
            await self._browser_manager.start()
        return self._browser_manager

    def _invalidate_probe(self):
        """Clear cached probe data (e.g. when changing episodes or seasons)."""
        self._probed_m3u8 = None
        self._probed_url = None
        self._ep_probes = {}

    @staticmethod
    def _resolve_quality(quality, quality_map):
        """Resolve requested quality against quality_map. Falls back to best available.
        Returns the resolved quality string."""
        if not quality_map or quality in quality_map:
            return quality
        avail = sorted(quality_map.keys(), key=lambda q: int(q), reverse=True)
        for q in avail:
            if int(q) <= int(quality):
                return q
        return avail[-1] if avail else quality

    async def _probe_qualities(self, page_url):
        """Extract m3u8 and parse real quality levels. Results are cached per URL.
        Returns (master_url, quality_map, best_quality) or (None, None, None)."""
        if self._probed_url == page_url and self._probed_m3u8 is not None:
            return self._probed_m3u8
        browser = await self._get_browser()
        result = await extract_m3u8_url(browser, page_url)
        if result[0]:
            self._probed_m3u8 = result
            self._probed_url = page_url
        return result

    @staticmethod
    def _get_quality_url(quality, quality_map, master_url):
        """Get the actual stream URL for the selected quality.
        If a child URI exists for this quality, use it (direct stream).
        Otherwise, return the master URL (player handles ABR)."""
        if quality_map and quality in quality_map:
            child_uri = quality_map[quality].get('uri')
            if child_uri:
                return child_uri
        return master_url

    async def _search_and_select(self):
        """Search + display results with category metadata + select.
        Returns False if user wants to exit."""
        query = console.input("\n[cyan]Enter the name (or [red]exit[/red] to quit)[red]:[/red] ")
        if query.lower() == 'exit':
            return False
        results = await search(query)
        if not results:
            console.print("[red]No results found.[/red]")
            return True

        # Build Rich table with category metadata
        table = Table(title="Search Results", title_style="bold magenta",
                       border_style="dim", show_lines=False, pad_edge=False)
        table.add_column("#", style="blue", justify="center", width=4)
        table.add_column("", width=3)  # icon column
        table.add_column("Title", style="white", min_width=30)
        table.add_column("Category", style="dim", justify="right")

        for idx, (title, url) in enumerate(results, 1):
            icon, cat_label = _extract_category(url)
            table.add_row(str(idx), icon, title, cat_label)

        console.print(table)
        try:
            choice = int(console.input("\nChoose a number: ")) - 1
            selected_title, selected_url = results[choice]
        except (ValueError, IndexError):
            console.print("[red]Invalid selection![/red]")
            return True
        seasons = await extract_seasons(selected_url)
        self.current_series = {'title': selected_title, 'url': selected_url, 'seasons': seasons}
        self.is_movie = not bool(seasons)
        return True

    @staticmethod
    def _select_quality(quality_map=None):
        """Quality selection. If quality_map provided (from master.m3u8 parse),
        shows real detected resolutions. Otherwise shows defaults.
        Returns quality string (e.g. '1080') or empty on invalid input."""
        if quality_map and len(quality_map) > 1:
            # Real qualities detected from master playlist
            sorted_qs = sorted(quality_map.keys(), key=lambda q: int(q), reverse=True)
            console.print("\n[green]Available qualities (detected from stream):[/green]")
            quality_map_list = {}
            for idx, q in enumerate(sorted_qs, 1):
                console.print(f"[white][[blue]{idx}[/blue]] {q}p[/white]")
                quality_map_list[str(idx)] = q
            quality_choice = console.input("[cyan]Choose quality number [red]:[/red][/cyan] ")
            if quality_choice not in quality_map_list:
                console.print(f"[red]Invalid choice! Please enter 1-{len(sorted_qs)}.[/red]")
                return ''
            return quality_map_list[quality_choice]
        elif quality_map and len(quality_map) == 1:
            # Only one quality available
            only_q = list(quality_map.keys())[0]
            console.print(f"\n[green]Only one quality available: {only_q}p[/green]")
            return only_q
        else:
            # Fallback: hardcoded defaults (no quality map yet)
            console.print("\n[green]Available qualities:[/green]")
            console.print("[white][[blue]1[/blue]] 1080p[/white]")
            console.print("[white][[blue]2[/blue]] 720p[/white]")
            console.print("[white][[blue]3[/blue]] 360p[/white]")
            quality_choice = console.input("[cyan]Choose quality number [red]:[/red][/cyan] ")
            quality_map_fallback = {'1': '1080', '2': '720', '3': '360'}
            if quality_choice not in quality_map_fallback:
                console.print("[red]Invalid quality choice! Please enter 1, 2, or 3.[/red]")
                return ''
            return quality_map_fallback[quality_choice]

    @staticmethod
    def _select_action():
        """Action menu (download/stream/copy). Returns action string."""
        console.print("\n" + "="*50)
        table = Table(title="Choose Action", title_style="bold cyan", border_style="dim")
        table.add_column("#", style="blue", justify="center", width=4)
        table.add_column("Action", style="white")
        table.add_row("1", "Download video to disk")
        table.add_row("2", "Stream to local media player")
        table.add_row("3", "Stream via FaselHD Mini Player (built-in)")
        table.add_row("4", "Copy m3u8 URL to clipboard")
        console.print(table)
        return console.input("[cyan]Choose action number [red]:[/red] ")

    @staticmethod
    def _copy_to_clipboard(text):
        """Copy text to clipboard (Windows)."""
        try:
            import pyperclip
            pyperclip.copy(text)
        except ImportError:
            process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
            process.communicate(text.encode('utf-8'))
        console.print("[green]Copied to clipboard![/green]")
        console.print(f"[dim]{text}[/dim]")

    async def _execute_movie_action(self, action, quality, master_url, quality_map):
        """Execute an action for the selected movie. Uses pre-probed m3u8 data."""
        movie_name = re.sub(r'[^a-zA-Z0-9_]', '', self.current_series['title'].replace(" ", "_"))
        actual_url = self._get_quality_url(quality, quality_map, master_url)

        if action == '1':
            # Download: use child URI for specific quality when available
            download_url = actual_url
            output_path = os.path.expanduser(f"~/Downloads/{movie_name}_{quality}.mp4")
            ffmpeg_path = ensure_ffmpeg()
            downloadm3u8_path = None
            if hasattr(sys, '_MEIPASS'):
                downloadm3u8_path = os.path.join(sys._MEIPASS, "downloadm3u8.exe")
            elif os.path.isfile("downloadm3u8.exe"):
                downloadm3u8_path = "downloadm3u8.exe"

            if downloadm3u8_path:
                command = [downloadm3u8_path, '-o', output_path, download_url]
            elif ffmpeg_path:
                command = [
                    ffmpeg_path, '-i', download_url,
                    '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
                    '-progress', 'pipe:1', '-y', output_path
                ]
            else:
                console.print("[red]No download tool available.[/red]")
                return

            console.print(f"[green]Downloading {quality}p → {os.path.basename(output_path)}[/green]")
            console.print(f"[dim]URL: {download_url}[/dim]")

            for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
                process = await asyncio.create_subprocess_exec(
                    *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                )
                with Progress(
                    TextColumn("[progress.description]{task.description}", style="white"),
                    TightBarColumn(width=40),
                    TextColumn("{task.percentage:>3.0f}%", style="bold white"),
                    TimeRemainingColumn()
                ) as progress:
                    task_id = progress.add_task(f"Downloading {movie_name}...", total=100)
                    last_pct = 0
                    while True:
                        line_bytes = await process.stdout.readline()
                        if not line_bytes:
                            break
                        line = line_bytes.decode('utf-8', errors='replace')
                        m = re.search(r'(\d{1,3})%', line)
                        if m:
                            pct = int(m.group(1))
                            if pct > last_pct:
                                progress.update(task_id, completed=pct)
                                last_pct = pct
                        if 'Download completed' in line:
                            progress.update(task_id, completed=100)
                            break
                await process.wait()
                if process.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                    console.print(f"[green]Download complete: {output_path}[/green]")
                    return
                if os.path.isfile(output_path):
                    try: os.unlink(output_path)
                    except Exception: pass
                if attempt < MAX_DOWNLOAD_RETRIES:
                    console.print(f"[yellow]Retry {attempt}/{MAX_DOWNLOAD_RETRIES} in {3*attempt}s...[/yellow]")
                    await asyncio.sleep(3 * attempt)
                else:
                    console.print(f"[red]Download failed after {MAX_DOWNLOAD_RETRIES} attempts.[/red]")

        elif action == '2':
            # Stream: pass child URI or master URL
            console.print(f"[green]Streaming {quality}p...[/green]")
            stream_to_player(actual_url)
        elif action == '3':
            console.print(f"\n[cyan]Launching Mini Player ({quality}p)...[/cyan]")
            launch_mini_player(actual_url, movie_name)
        elif action == '4':
            self._copy_to_clipboard(actual_url)
        else:
            console.print("[red]Invalid action![/red]")

    async def _pre_probe_all_episodes(self):
        """Batch pre-probe all selected episodes. Shows a clean result table.
        Populates self._ep_probes cache. Returns merged quality_map from first
        successful probe, or None if all probes failed.
        Uses plain console.print status lines — NO spinners near input areas."""
        self._ep_probes = {}
        ep_urls = [(self._stored_episodes[ep_idx], ep_idx)
                    for ep_idx in self._episode_indices
                    if 0 <= ep_idx < len(self._stored_episodes)]
        if not ep_urls:
            return None

        total = len(ep_urls)
        console.print(f"\n[cyan]Probing {total} episode{'s' if total > 1 else ''}...[/cyan]")

        browser = await self._get_browser()
        results = {}  # ep_idx -> (success, ep_label, quality_str or error)

        # Probe episodes one at a time (sequential to avoid overwhelming browser)
        for i, (ep_url, ep_idx) in enumerate(ep_urls):
            ep_label = f"E{ep_idx + 1:02d}"
            console.print(f"  [dim][{i+1}/{total}] Probing {ep_label}...[/dim]")
            master, qmap, best = await extract_m3u8_url(browser, ep_url)
            if master and qmap:
                self._ep_probes[ep_url] = (master, qmap, best)
                avail_qs = sorted(qmap.keys(), key=lambda q: int(q), reverse=True)
                q_str = ', '.join(f"{q}p" for q in avail_qs)
                results[ep_idx] = (True, ep_label, q_str)
            else:
                results[ep_idx] = (False, ep_label, "failed")

        # ── Display clean result table ──
        table = Table(title="Probe Results", title_style="bold cyan", border_style="dim", show_lines=True)
        table.add_column("Episode", style="white", justify="center", width=8)
        table.add_column("Status", justify="center", width=6)
        table.add_column("Available Qualities", style="white")

        success_count = 0
        fail_count = 0
        for ep_idx in self._episode_indices:
            if 0 <= ep_idx < len(self._stored_episodes):
                ok, label, info = results.get(ep_idx, (False, f"E{ep_idx+1:02d}", "skipped"))
                if ok:
                    table.add_row(label, "[green]OK[/green]", info)
                    success_count += 1
                else:
                    table.add_row(label, "[red]FAIL[/red]", f"[red]{info}[/red]")
                    fail_count += 1
        console.print(table)
        console.print(f"  [green]{success_count}/{total}[/green] episodes ready"
                      + (f" [red]({fail_count} failed)[/red]" if fail_count else ""))

        # Filter out failed episodes from selection
        if fail_count > 0:
            good_indices = [idx for idx in self._episode_indices
                           if 0 <= idx < len(self._stored_episodes) and results.get(idx, (False,))[0]]
            removed = [idx + 1 for idx in self._episode_indices
                       if 0 <= idx < len(self._stored_episodes) and not results.get(idx, (False,))[0]]
            self._episode_indices = good_indices
            if removed:
                console.print(f"[yellow]Removed failed episodes: {', '.join(str(x) for x in removed)}[/yellow]")

        if not self._ep_probes:
            return None

        # Return merged quality map from first successful probe
        first_url = ep_urls[0][0]
        if first_url in self._ep_probes:
            return self._ep_probes[first_url][1]
        return list(self._ep_probes.values())[0][1]

    async def _execute_series_action(self, action, quality):
        """Execute an action for the selected series episodes.
        Uses pre-probed cache (self._ep_probes) — zero re-probing.
        Falls back to fresh probe only if cache miss (shouldn't happen after pre-probe phase)."""
        title = re.sub(r'[^a-zA-Z0-9_]', '', self.current_series['title'].replace(" ", "_"))

        # Build episode list from pre-probed cache (already validated + filtered by pre-probe)
        ep_tasks = []  # list of (ep_idx, ep_url, master, qmap, video_name)
        for ep_idx in self._episode_indices:
            if 0 <= ep_idx < len(self._stored_episodes):
                ep_url = self._stored_episodes[ep_idx]
                cached = self._ep_probes.get(ep_url)
                if cached:
                    master, qmap, best = cached
                    video_name = f"{title}_S{self._season_number:02d}_E{ep_idx+1:02d}"
                    ep_tasks.append((ep_idx, ep_url, master, qmap, video_name))
        if not ep_tasks:
            console.print("[red]No episodes ready for action.[/red]")
            return

        if action == '1':
            # ── Download: all progress bars together, NO re-probing ──
            sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
            errors = []  # Collect errors instead of printing mid-download

            progress = Progress(
                TextColumn("[progress.description]{task.description}", style="white"),
                TightBarColumn(width=40),
                TextColumn("{task.percentage:>3.0f}%", style="bold white"),
                TimeRemainingColumn()
            )

            async def _dl_episode(ep_url, video_name, ep_master, ep_qmap, progress):
                """Download a single episode using pre-probed data. No re-probing."""
                async with sem:
                    ep_quality = self._resolve_quality(quality, ep_qmap)
                    dl_url = self._get_quality_url(ep_quality, ep_qmap, ep_master)
                    output_path = os.path.expanduser(f"~/Downloads/{video_name}_{ep_quality}.mp4")
                    ffmpeg_path = ensure_ffmpeg()
                    dl_tool = None
                    if hasattr(sys, '_MEIPASS'):
                        dl_tool = os.path.join(sys._MEIPASS, "downloadm3u8.exe")
                    elif os.path.isfile("downloadm3u8.exe"):
                        dl_tool = "downloadm3u8.exe"

                    if dl_tool:
                        cmd = [dl_tool, '-o', output_path, dl_url]
                    elif ffmpeg_path:
                        cmd = [ffmpeg_path, '-i', dl_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc',
                               '-progress', 'pipe:1', '-y', output_path]
                    else:
                        errors.append(f"No download tool for {video_name}")
                        return

                    # Extract clean episode label: S01E05 from _Invincible_S01_E05
                    ep_tag = re.search(r'(S\d+E\d+)', video_name)
                    ep_label = ep_tag.group(1) if ep_tag else video_name
                    task_id = progress.add_task(f"{ep_label} [{ep_quality}p] downloading", total=100)

                    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
                        if attempt > 1:
                            progress.update(task_id, completed=0,
                                            description=f"{ep_label} [{ep_quality}p] retry {attempt}/{MAX_DOWNLOAD_RETRIES}")
                        try:
                            proc = await asyncio.create_subprocess_exec(
                                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                            )
                        except Exception as e:
                            errors.append(f"{ep_label} failed to launch: {e}")
                            break
                        last_pct = 0
                        try:
                            while True:
                                line_bytes = await proc.stdout.readline()
                                if not line_bytes:
                                    break
                                line = line_bytes.decode('utf-8', errors='replace')
                                m = re.search(r'(\d{1,3})%', line)
                                if m and int(m.group(1)) > last_pct:
                                    progress.update(task_id, completed=int(m.group(1)))
                                    last_pct = int(m.group(1))
                                if 'Download completed' in line:
                                    progress.update(task_id, completed=100)
                                    break
                            await proc.wait()
                        except Exception:
                            try:
                                proc.kill()
                                await proc.wait()
                            except Exception:
                                pass
                        if proc.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
                            progress.update(task_id, description=f"{ep_label} [{ep_quality}p] done")
                            return
                        if os.path.isfile(output_path):
                            try: os.unlink(output_path)
                            except Exception: pass
                        if attempt < MAX_DOWNLOAD_RETRIES:
                            progress.update(task_id, completed=0,
                                            description=f"{ep_label} [{ep_quality}p] waiting {3*attempt}s...")
                            await asyncio.sleep(3 * attempt)
                        else:
                            progress.update(task_id, description=f"{ep_label} [{ep_quality}p] failed")
                            errors.append(f"{ep_label} failed after {MAX_DOWNLOAD_RETRIES} retries")

            tasks = []
            with progress:
                for ep_idx, ep_url, ep_master, ep_qmap, video_name in ep_tasks:
                    tasks.append(_dl_episode(ep_url, video_name, ep_master, ep_qmap, progress))
                await asyncio.gather(*tasks)

            # Show error summary after progress exits (clean, no interleaving)
            if errors:
                console.print(f"\n[yellow]Download summary: {len(ep_tasks) - len(errors)}/{len(ep_tasks)} succeeded[/yellow]")
                for err in errors:
                    console.print(f"  [red]x {err}[/red]")
            else:
                console.print(f"\n[green]All {len(ep_tasks)} episodes downloaded successfully.[/green]")

        elif action == '2':
            # ── Stream: sequential, uses cached data ──
            for ep_idx, ep_url, ep_master, ep_qmap, video_name in ep_tasks:
                ep_quality = self._resolve_quality(quality, ep_qmap)
                ep_url_actual = self._get_quality_url(ep_quality, ep_qmap, ep_master)
                console.print(f"\n[green]Streaming {ep_quality}p:[/green] [cyan]{video_name}[/cyan]")
                stream_to_player(ep_url_actual)

        elif action == '3':
            # ── Mini Player: sequential, uses cached data ──
            for ep_idx, ep_url, ep_master, ep_qmap, video_name in ep_tasks:
                ep_quality = self._resolve_quality(quality, ep_qmap)
                ep_url_actual = self._get_quality_url(ep_quality, ep_qmap, ep_master)
                console.print(f"\n[cyan]Mini Player:[/cyan] [white]{video_name} ({ep_quality}p)[/white]")
                launch_mini_player(ep_url_actual, video_name)

        elif action == '4':
            # ── Copy URLs: all at once from cache ──
            urls = []
            console.print(f"\n[cyan]Stream URLs ({len(ep_tasks)} episodes):[/cyan]")
            for ep_idx, ep_url, ep_master, ep_qmap, video_name in ep_tasks:
                ep_quality = self._resolve_quality(quality, ep_qmap)
                ep_url_actual = self._get_quality_url(ep_quality, ep_qmap, ep_master)
                urls.append(ep_url_actual)
                console.print(f"  [green]{video_name}:[/green] [dim]{ep_url_actual}[/dim]")
            if urls:
                self._copy_to_clipboard("\n".join(urls))
            else:
                console.print("[red]No URLs to copy.[/red]")
        else:
            console.print("[red]Invalid action![/red]")

    async def _movie_flow(self):
        """Movie state machine: probe -> quality -> action -> next."""
        state = 'probe'
        quality = '1080'
        master_url = None
        quality_map = None
        while True:
            if state == 'probe':
                console.print("[cyan]Probing stream for quality detection...[/cyan]")
                master_url, quality_map, best_quality = await self._probe_qualities(self.current_series['url'])
                if not master_url:
                    console.print("[red]Failed to extract stream URL.[/red]")
                    self.current_series = None
                    return
                state = 'quality'
            elif state == 'quality':
                quality = self._select_quality(quality_map)
                if not quality:
                    continue
                state = 'action'
            elif state == 'action':
                action = self._select_action()
                await self._execute_movie_action(action, quality, master_url, quality_map)
                state = 'next'
            elif state == 'next':
                console.print("\n[green]What would you like to do next?[/green]")
                console.print("[white][[blue]1[/blue]] Choose another action (download/stream/copy)[/white]")
                console.print("[white][[blue]2[/blue]] Choose different quality[/white]")
                console.print("[white][[blue]3[/blue]] Search again[/white]")
                console.print("[white][[blue]4[/blue]] Exit[/white]")
                choice = console.input("[cyan]Enter your choice [red]:[/red][/cyan] ")
                if choice == '1':
                    state = 'action'
                elif choice == '2':
                    state = 'quality'
                elif choice == '3':
                    self.current_series = None
                    self._invalidate_probe()
                    return
                elif choice == '4':
                    self._exiting = True
                    return
                else:
                    console.print("[red]Invalid choice![/red]")

    async def _series_flow(self):
        """Series state machine: season -> episode -> probe -> quality -> action -> next."""
        state = 'season'
        quality = '1080'
        series_quality_map = None
        while True:
            if state == 'season':
                self._invalidate_probe()
                console.print(f"\n[yellow]Found {len(self.current_series['seasons'])} seasons:[/yellow]")
                for idx, link in enumerate(self.current_series['seasons'], 1):
                    console.print(f"[blue]{idx}[/blue][red]:[/red][white] {link}[/white]")
                season_choice = console.input(
                    "\n[cyan]Choose season number (or [bright_red]back[/bright_red] to search again)[red]:[/red][/cyan] "
                )
                if season_choice.lower() == 'back':
                    self.current_series = None
                    return
                try:
                    season_index = int(season_choice) - 1
                    self._season_number = season_index + 1
                    selected_season_url = self.current_series['seasons'][season_index]
                except (ValueError, IndexError):
                    console.print("[red]Invalid season selection![/red]")
                    continue
                episodes_raw = await extract_episodes(selected_season_url)
                episode_links = [l for l in episodes_raw if "episodes" in l]
                if not episode_links:
                    console.print("[red]No episodes found.[/red]")
                    continue
                # Deduplicate
                seen = set()
                self._stored_episodes = []
                for link in episode_links:
                    norm = link.rstrip('/').lower()
                    if norm not in seen:
                        seen.add(norm)
                        self._stored_episodes.append(link)
                state = 'episode'
            elif state == 'episode':
                console.print(f"\n[yellow]Found {len(self._stored_episodes)} episodes:[/yellow]")
                for idx, link in enumerate(self._stored_episodes, 1):
                    console.print(f"[blue]{idx}[/blue][red]:[/red][white] {unquote(link)}[/white]")
                episodes_input = console.input(
                    "\n[cyan]Enter episode numbers (e.g., 1,3,5-8 or [bright_red]all[/bright_red])[red]:[/red][/cyan] "
                )
                parsed = _parse_episode_input(episodes_input, len(self._stored_episodes))
                if parsed is None:
                    console.print("[red]Invalid input! Use numbers like 1,3,5-8 or 'all'.[/red]")
                    continue
                if isinstance(parsed, tuple):
                    self._episode_indices, invalid = parsed
                    bad_nums = ', '.join(str(i + 1) for i in invalid)
                    console.print(f"[yellow]Episode(s) {bad_nums} are out of range (max {len(self._stored_episodes)}), skipping them.[/yellow]")
                else:
                    self._episode_indices = parsed
                if not self._episode_indices:
                    console.print("[red]No valid episodes selected.[/red]")
                    continue
                # ── Selection summary (Plan B) ──
                ep_label = _format_episode_list(self._episode_indices, len(self._stored_episodes))
                title_short = self.current_series['title'][:40]
                console.print(Panel(
                    f"[white]Series:[/white] [cyan]{title_short}[/cyan]\n"
                    f"[white]Season:[/white] [cyan]{self._season_number}[/cyan]\n"
                    f"[white]Episodes:[/white] [cyan]{ep_label}[/cyan] [dim]({len(self._episode_indices)} episodes)[/dim]",
                    title="Selection", border_style="green"
                ))
                confirm = console.input("[cyan]Confirm? ([green]Y[/green]/[red]n[/red], or re-enter)[red]:[/red] ")
                if confirm.lower().strip() in ('n', 'no'):
                    continue
                # ── Batch pre-probe (Plan C) ──
                series_quality_map = await self._pre_probe_all_episodes()
                if series_quality_map is None:
                    # All probes failed
                    console.print("[red]Failed to probe any episode. Cannot continue.[/red]")
                    continue
                state = 'quality'
            elif state == 'quality':
                quality = self._select_quality(series_quality_map)
                if not quality:
                    continue
                state = 'action'
            elif state == 'action':
                action = self._select_action()
                await self._execute_series_action(action, quality)
                state = 'next'
            elif state == 'next':
                console.print("\n[green]What would you like to do next?[/green]")
                console.print("[white][[blue]1[/blue]] Choose another action (download/stream/copy)[/white]")
                console.print("[white][[blue]2[/blue]] Choose different quality[/white]")
                console.print("[white][[blue]3[/blue]] Choose other episodes[/white]")
                console.print("[white][[blue]4[/blue]] Choose another season[/white]")
                console.print("[white][[blue]5[/blue]] Search again[/white]")
                console.print("[white][[blue]6[/blue]] Exit[/white]")
                choice = console.input("[cyan]Enter your choice [red]:[/red][/cyan] ")
                if choice == '1':
                    state = 'action'
                elif choice == '2':
                    state = 'quality'
                elif choice == '3':
                    state = 'episode'
                elif choice == '4':
                    state = 'season'
                elif choice == '5':
                    self.current_series = None
                    return
                elif choice == '6':
                    self._exiting = True
                    return
                else:
                    console.print("[red]Invalid choice![/red]")

    async def _show_trending_and_pick(self):
        """Fetch and display trending with category metadata. Returns (title, url) or None."""
        console.print("[cyan]Loading trending...[/cyan]")
        trending = await fetch_trending()
        if not trending:
            console.print("[yellow]Could not load trending.[/yellow]")
            return None

        table = Table(title="Trending Now", title_style="bold magenta",
                       border_style="dim", show_lines=False, pad_edge=False)
        table.add_column("#", style="blue", justify="center", width=4)
        table.add_column("", width=3)  # icon column
        table.add_column("Title", style="white", min_width=30)
        table.add_column("Category", style="dim", justify="right")

        for idx, (title, url) in enumerate(trending, 1):
            icon, cat_label = _extract_category(url)
            table.add_row(str(idx), icon, title, cat_label)

        console.print(table)
        console.print("[dim]Pick a number, or press Enter to go back.[/dim]")
        pick = console.input("[cyan]Pick trending number[/cyan][red]:[/red] ")
        if pick.strip():
            try:
                pick_idx = int(pick.strip()) - 1
                if 0 <= pick_idx < len(trending):
                    return trending[pick_idx]
            except ValueError:
                pass
        return None

    async def _main_menu(self):
        """Main menu: search or trending. Returns 'exit' if user wants to quit."""
        console.print("\n" + "=" * 50)
        table = Table(title="Main Menu", title_style="bold cyan", border_style="dim")
        table.add_column("#", style="blue", justify="center", width=4)
        table.add_column("Option", style="white")
        table.add_row("1", "Search for a movie/series")
        table.add_row("2", "Browse trending")
        table.add_row("3", "Exit")
        console.print(table)
        choice = console.input("[cyan]Choose option [red]:[/red] ")
        if choice == '1':
            return 'search'
        elif choice == '2':
            return 'trending'
        elif choice == '3':
            return 'exit'
        else:
            # Default: treat as search
            return 'search'

    async def run(self):
        """Main application loop — search or browse trending."""
        try:
            while not self._exiting:
                if self.current_series is None:
                    action = await self._main_menu()
                    if action == 'exit':
                        return
                    elif action == 'trending':
                        pick = await self._show_trending_and_pick()
                        if pick:
                            t_title, t_url = pick
                            # Check if it's a series or movie by fetching
                            seasons = await extract_seasons(t_url)
                            self.current_series = {'title': t_title, 'url': t_url, 'seasons': seasons}
                            self.is_movie = not bool(seasons)
                            self._invalidate_probe()
                            continue
                        else:
                            continue  # Back to main menu
                    elif action == 'search':
                        if not await self._search_and_select():
                            return
                if self.is_movie:
                    await self._movie_flow()
                else:
                    await self._series_flow()
                if self.current_series is None:
                    continue
        finally:
            await self.close()

    async def close(self):
        """Clean shutdown — close browsers, restore console."""
        if self._browser_manager:
            await self._browser_manager.close()
            self._browser_manager = None
        await _close_cf_session()


if __name__ == "__main__":
    app = FaselHDApp()
    asyncio.run(app.run())
