#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FaselHD Mini Player v2 - Built-in media player for streaming m3u8 URLs.
Uses tkinter for GUI and python-vlc (or mpv) for playback.
If neither is available, warns the user instead of silently opening the browser.

Features:
  - Seek bar with time display
  - Volume slider + mute toggle
  - Keyboard shortcuts (Space, arrows, +/-, F11, Escape, M)
  - Episode name in title bar
  - Auto-reconnect on stream drop
  - Quality indicator
  - Polished dark UI

Usage:
    python mini_player.py <m3u8_url> [title]
"""

import sys
import os
import subprocess
import threading
import time
import re


def _find_mpv():
    """Check if mpv is available on PATH."""
    import shutil
    return shutil.which("mpv") is not None


def _ms_to_str(ms):
    """Convert milliseconds to HH:MM:SS string."""
    if ms < 0:
        ms = 0
    total_sec = int(ms / 1000)
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python mini_player.py <m3u8_url> [title]")
        sys.exit(1)

    m3u8_url = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else ""

    # Try python-vlc first (best HLS support on Windows)
    try:
        import vlc
        _launch_vlc_player(m3u8_url, vlc, title)
        return
    except ImportError:
        pass

    # Try mpv as subprocess (great HLS support, lightweight)
    if _find_mpv():
        _launch_mpv_player(m3u8_url, title)
        return

    # No playback engine found — warn user, don't silently open browser
    _show_no_engine_dialog(m3u8_url, title)


def _show_no_engine_dialog(url, title):
    """Show a tkinter dialog explaining no player engine is found."""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        print("=" * 50)
        print("  FaselHD Mini Player")
        print("=" * 50)
        print("No playback engine found!")
        print("")
        print("Install one of these for m3u8 streaming:")
        print("  1. VLC:  pip install python-vlc")
        print("     + install VLC player from videolan.org")
        print("  2. mpv:  download from mpv.io, add to PATH")
        print("")
        print("Falling back to system default (may open browser)...")
        print("=" * 50)
        try:
            os.startfile(url)
        except Exception:
            pass
        return

    root = tk.Tk()
    root.title("FaselHD Mini Player - No Engine")
    root.geometry("420x320")
    root.configure(bg="#0d1117")
    root.resizable(False, False)

    tk.Label(root, text="FaselHD Mini Player", bg="#0d1117", fg="#58a6ff",
             font=("Segoe UI", 16, "bold")).pack(pady=(20, 5))
    tk.Label(root, text="No playback engine found!", bg="#0d1117", fg="#f85149",
             font=("Segoe UI", 11)).pack(pady=(0, 15))

    info_text = (
        "Install one of these for m3u8 streaming:\n\n"
        "  1. VLC Player\n"
        "     pip install python-vlc\n"
        "     + install VLC from videolan.org\n\n"
        "  2. mpv Player\n"
        "     Download from mpv.io\n"
        "     Add to system PATH"
    )
    tk.Label(root, text=info_text, bg="#0d1117", fg="#c9d1d9",
             font=("Segoe UI", 9), justify=tk.LEFT).pack(padx=20, anchor="w")

    def open_in_browser():
        try:
            os.startfile(url)
        except Exception:
            pass
        root.destroy()

    def do_nothing():
        root.destroy()

    btn_frame = tk.Frame(root, bg="#0d1117")
    btn_frame.pack(pady=15)
    tk.Button(btn_frame, text="Open in Browser", command=open_in_browser,
              bg="#21262d", fg="#c9d1d9", font=("Segoe UI", 9), padx=15, pady=5,
              relief=tk.FLAT, activebackground="#30363d").pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="Close", command=do_nothing,
              bg="#21262d", fg="#c9d1d9", font=("Segoe UI", 9), padx=15, pady=5,
              relief=tk.FLAT, activebackground="#30363d").pack(side=tk.LEFT, padx=5)

    root.mainloop()


def _launch_mpv_player(url, title):
    """Launch mpv as a subprocess (mpv has great built-in HLS support)."""
    mpv_path = subprocess.getoutput("where mpv").strip().splitlines()[0].strip()
    window_title = f"FaselHD - {title}" if title else "FaselHD Mini Player"
    subprocess.Popen([
        mpv_path,
        f"--title={window_title}",
        "--force-window=immediate",
        "--keep-open=yes",
        "--osc=yes",
        url
    ])


def _launch_vlc_player(url, vlc_module, title):
    """Launch a tkinter window with embedded VLC player.
    Full-featured: seek bar, time, volume, keyboard shortcuts, auto-reconnect."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        _show_no_engine_dialog(url, title)
        return

    root = tk.Tk()
    window_title = f"FaselHD - {title}" if title else "FaselHD Mini Player"
    root.title(window_title)
    root.geometry("960x580")
    root.configure(bg="black")
    root.minsize(640, 400)

    # ── VLC instance and player ──
    instance = vlc_module.Instance("--network-caching=5000")
    player = instance.media_player_new()
    media = instance.media_new(url)
    player.set_media(media)

    # ── State ──
    state = {
        "playing": False,
        "fullscreen": False,
        "seeking": False,
        "reconnect_attempts": 0,
        "max_reconnect": 3,
        "closed": False,
        "url": url,
    }

    # ── Video canvas ──
    video_frame = tk.Frame(root, bg="black")
    video_frame.pack(fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(video_frame, bg="black", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True)

    # ── Styles ──
    style = ttk.Style()
    style.theme_use('clam')
    style.configure("Dark.TButton", background="#161b22", foreground="#e6edf3",
                    borderwidth=0, padding=6, font=("Segoe UI", 10))
    style.map("Dark.TButton", background=[("active", "#30363d")])
    style.configure("Dark.TLabel", background="#0d1117", foreground="#8b949e",
                    font=("Segoe UI", 9))
    style.configure("Time.TLabel", background="#0d1117", foreground="#e6edf3",
                    font=("Consolas", 9))
    style.configure("Status.TLabel", background="#0d1117", foreground="#58a6ff",
                    font=("Segoe UI", 9))
    style.configure("Volume.Horizontal.TScale", background="#0d1117",
                    troughcolor="#21262d")

    # ── Bottom control area ──
    bottom = tk.Frame(root, bg="#0d1117")
    bottom.pack(fill=tk.X, side=tk.BOTTOM)

    # Seek bar row
    seek_frame = tk.Frame(bottom, bg="#0d1117")
    seek_frame.pack(fill=tk.X, padx=10, pady=(6, 0))

    time_current_var = tk.StringVar(value="00:00")
    time_total_var = tk.StringVar(value="00:00")

    ttk.Label(seek_frame, textvariable=time_current_var,
              style="Time.TLabel").pack(side=tk.LEFT)

    seek_var = tk.DoubleVar(value=0)
    seek_scale = ttk.Scale(seek_frame, from_=0, to=1000, variable=seek_var,
                           orient=tk.HORIZONTAL, style="Volume.Horizontal.TScale",
                           command=_on_seek)
    seek_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

    ttk.Label(seek_frame, textvariable=time_total_var,
              style="Time.TLabel").pack(side=tk.LEFT)

    # Controls row
    ctrl_frame = tk.Frame(bottom, bg="#0d1117", height=44)
    ctrl_frame.pack(fill=tk.X, padx=10, pady=(4, 8))

    # Play/Pause
    play_btn = ttk.Button(ctrl_frame, text="\u25B6", command=toggle_play,
                          style="Dark.TButton", width=3)
    play_btn.pack(side=tk.LEFT, padx=(0, 4))

    # Stop
    stop_btn = ttk.Button(ctrl_frame, text="\u23F9", command=stop,
                          style="Dark.TButton", width=3)
    stop_btn.pack(side=tk.LEFT, padx=4)

    # Volume
    vol_var = tk.IntVar(value=100)
    vol_btn = ttk.Button(ctrl_frame, text="\U0001F50A", command=toggle_mute,
                         style="Dark.TButton", width=3)
    vol_btn.pack(side=tk.LEFT, padx=(12, 4))

    vol_scale = ttk.Scale(ctrl_frame, from_=0, to=100, variable=vol_var,
                          orient=tk.HORIZONTAL, style="Volume.Horizontal.TScale",
                          command=_on_volume, length=100)
    vol_scale.pack(side=tk.LEFT, padx=4)

    # Status / quality
    status_var = tk.StringVar(value="Connecting...")
    status_label = ttk.Label(ctrl_frame, textvariable=status_var, style="Status.TLabel")
    status_label.pack(side=tk.RIGHT, padx=(10, 0))

    # ── Functions ──

    def toggle_play():
        if state["playing"]:
            player.pause()
            play_btn.configure(text="\u25B6")
            state["playing"] = False
        else:
            player.play()
            play_btn.configure(text="\u23F8")
            state["playing"] = True

    def stop():
        player.stop()
        play_btn.configure(text="\u25B6")
        state["playing"] = False
        status_var.set("Stopped")

    def toggle_mute():
        if player.audio_get_mute():
            player.audio_set_mute(False)
            vol_btn.configure(text="\U0001F50A")
            vol_scale.set(vol_var.get())
        else:
            player.audio_set_mute(True)
            vol_btn.configure(text="\U0001F507")

    def _on_seek(val):
        if state["seeking"]:
            return
        state["seeking"] = True
        # Convert 0-1000 scale to 0.0-1.0
        pos = float(val) / 1000.0
        player.set_position(pos)
        # Reset seeking after short delay (avoid feedback loop)
        root.after(300, lambda: state.update(seeking=False))

    def _on_volume(val):
        vol = int(float(val))
        player.audio_set_volume(vol)
        vol_var.set(vol)
        # Unmute if volume changes while muted
        if player.audio_get_mute() and vol > 0:
            player.audio_set_mute(False)
            vol_btn.configure(text="\U0001F50A")

    def toggle_fullscreen(event=None):
        if state["fullscreen"]:
            root.attributes("-fullscreen", False)
            state["fullscreen"] = False
            bottom.pack(fill=tk.X, side=tk.BOTTOM)
        else:
            root.attributes("-fullscreen", True)
            state["fullscreen"] = True
            bottom.pack_forget()

    def on_close():
        state["closed"] = True
        player.stop()
        player.release()
        instance.release()
        root.destroy()

    # ── Keyboard shortcuts ──
    root.bind("<F11>", lambda e: toggle_fullscreen())
    root.bind("<Escape>", lambda e: (
        toggle_fullscreen() if state["fullscreen"] else on_close()
    ))
    root.bind("<Space>", lambda e: toggle_play())
    root.bind("<Left>", lambda e: _seek_relative(-10))
    root.bind("<Right>", lambda e: _seek_relative(10))
    root.bind("<Up>", lambda e: _volume_relative(10))
    root.bind("<Down>", lambda e: _volume_relative(-10))
    root.bind("<plus>", lambda e: _volume_relative(10))
    root.bind("<equal>", lambda e: _volume_relative(10))
    root.bind("<minus>", lambda e: _volume_relative(-10))
    root.bind("<m>", lambda e: toggle_mute())
    root.bind("<M>", lambda e: toggle_mute())

    def _seek_relative(seconds):
        """Seek relative to current position (in seconds)."""
        try:
            current_ms = player.get_time()
            if current_ms < 0:
                current_ms = 0
            duration_ms = player.get_length()
            if duration_ms <= 0:
                return
            new_ms = max(0, min(current_ms + seconds * 1000, duration_ms))
            new_pos = new_ms / duration_ms
            player.set_position(new_pos)
        except Exception:
            pass

    def _volume_relative(delta):
        """Adjust volume by delta."""
        current = player.audio_get_volume()
        new_vol = max(0, min(150, current + delta))
        player.audio_set_volume(new_vol)
        vol_scale.set(new_vol)
        vol_var.set(new_vol)

    # ── Embed VLC into canvas ──
    def on_canvas_configure(event):
        if sys.platform == "win32":
            try:
                player.set_hwnd(canvas.winfo_id())
            except Exception:
                pass
        elif sys.platform == "linux":
            try:
                player.set_xwindow(canvas.winfo_id())
            except Exception:
                pass

    canvas.bind("<Configure>", on_canvas_configure)
    canvas.bind("<Double-Button-1>", lambda e: toggle_fullscreen())

    # ── Status update loop (runs every 500ms) ──
    def update_ui():
        if state["closed"]:
            return
        try:
            vlc_state = player.get_state()

            # Update play/pause button
            if vlc_state == vlc_module.State.Playing:
                if not state["playing"]:
                    play_btn.configure(text="\u23F8")
                    state["playing"] = True
                status_var.set("Playing")
            elif vlc_state == vlc_module.State.Paused:
                play_btn.configure(text="\u25B6")
                state["playing"] = False
                status_var.set("Paused")
            elif vlc_state == vlc_module.State.Buffering:
                status_var.set("Buffering...")
            elif vlc_state == vlc_module.State.Ended:
                play_btn.configure(text="\u25B6")
                state["playing"] = False
                status_var.set("Ended")
            elif vlc_state == vlc_module.State.Error:
                status_var.set("Error - stream may have dropped")
                _auto_reconnect()

            # Update seek bar + time (only if not user-seeking)
            if not state["seeking"]:
                current_ms = player.get_time()
                duration_ms = player.get_length()
                if duration_ms > 0 and current_ms >= 0:
                    pos = current_ms / duration_ms
                    seek_scale.set(pos * 1000)
                    time_current_var.set(_ms_to_str(current_ms))
                    time_total_var.set(_ms_to_str(duration_ms))
                elif current_ms >= 0:
                    time_current_var.set(_ms_to_str(current_ms))
                    # Live stream — show live indicator
                    if current_ms > 0:
                        time_total_var.set("LIVE")
        except Exception:
            pass

        root.after(500, update_ui)

    def _auto_reconnect():
        """Auto-reconnect when stream drops."""
        if state["reconnect_attempts"] >= state["max_reconnect"]:
            status_var.set(f"Stream failed after {state['max_reconnect']} reconnect attempts")
            return
        state["reconnect_attempts"] += 1
        attempt = state["reconnect_attempts"]
        status_var.set(f"Reconnecting... (attempt {attempt}/{state['max_reconnect']})")

        def do_reconnect():
            time.sleep(2)  # Brief pause before reconnect
            if state["closed"]:
                return
            try:
                new_media = instance.media_new(state["url"])
                player.set_media(new_media)
                player.play()
                root.after(0, lambda: status_var.set(f"Reconnected (attempt {attempt})"))
                # Reset reconnect counter on successful play
                time.sleep(3)
                if not state["closed"] and player.get_state() == vlc_module.State.Playing:
                    state["reconnect_attempts"] = 0
            except Exception:
                pass

        threading.Thread(target=do_reconnect, daemon=True).start()

    # ── Detect quality from URL ──
    quality_info = ""
    q_match = re.search(r'(\d{3,4})p?', url)
    if q_match:
        quality_info = f" | {q_match.group(1)}p"
    # Show quality in initial status
    if quality_info:
        status_var.set(f"Connecting...{quality_info}")

    # ── Start ──
    root.protocol("WM_DELETE_WINDOW", on_close)
    player.play()
    player.audio_set_volume(100)
    update_ui()

    root.mainloop()


if __name__ == "__main__":
    main()
