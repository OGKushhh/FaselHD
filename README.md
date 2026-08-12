<h1 align="center">
  <br>
  <img src="https://github.com/OGKushhh/FaselHD/blob/main/src/icon.ico" width="100">
  <br>
  FaselHD
  <br>  
</h1>
<p align="center">
  <a href="https://t.me/De3vil_3">
     <img src="https://img.shields.io/badge/De3vil_3-blue?style=for-the-badge&logo=Telegram&logoColor=00AEFF&labelColor=black&color=black">
  </a>
  <a href="https://www.facebook.com/De3vil.3">
     <img src="https://img.shields.io/badge/De3vil.3-blue?style=for-the-badge&logo=Facebook&logoColor=00AEFF&labelColor=black&color=black">
  </a>
  <a href="https://x.com/De3vil0">
     <img src="https://img.shields.io/badge/De3vil0-blue?style=for-the-badge&logo=x&logoColor=00AEFF&labelColor=black&color=black">
  </a>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/Original%20Author-De3vil-orange">
  <img src="https://img.shields.io/badge/Fork%20Maintainer-Abdo-blue">
  <img src="https://img.shields.io/badge/Written%20In-Python-blue?style=flat-square">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square">
</p>

### Description
A powerful CLI tool that searches, browses, and streams movies and series from FaselHD. Features automatic Cloudflare bypass, real-time quality detection from m3u8 master playlists, concurrent episode downloads, and multiple playback options including a built-in mini player.

### Features

- **Smart Cloudflare Bypass**  
  Uses a persistent browser session with lazy detection — solves Cloudflare challenges only when needed, then reuses the session for fast subsequent requests. Falls back to curl_cffi with TLS fingerprint impersonation if scrapling is unavailable.

- **Real-Time Quality Detection**  
  Parses m3u8 master playlists to detect actual available resolutions (240p–2160p) instead of guessing from URLs. Shows detected qualities before you choose.

- **Download Movies & Series**  
  Download movies or entire seasons with concurrent episode downloads (up to 3 parallel). Automatic retry on failure with progress tracking via rich.

- **Stream to Any Player**  
  Open streams directly in your preferred media player (VLC, PotPlayer, MPV, etc.) through the system "Open With" dialog.

- **Built-in Mini Player**  
  Stream directly inside FaselHD's embedded VLC-based mini player window — no external player needed.

- **Copy to Clipboard**  
  Copy the direct m3u8 stream URL to clipboard for use in any external player or tool.

- **Browse Trending**  
  Browse trending and recently added movies/series directly from the main page without searching.

- **Search with Caching**  
  Search results are cached for 5 minutes to avoid redundant page fetches when refining your selection.

- **Automatic ffmpeg Setup**  
  Auto-downloads ffmpeg on first run if not found in system PATH or imageio-ffmpeg cache. No manual setup required.

- **Interactive CLI**  
  Rich-powered terminal UI with colored tables, progress bars, and panels. Full Arabic/Unicode support on Windows with automatic console font and codepage configuration.

### Screenshots
<table align="center">
  <tr>
    <td align="center">
      <strong>1</strong><br>
      <img src="https://github.com/De3vil/Faselhd/blob/main/scr/1.jpg" alt="Image 1" width="500">
    </td>
    <td align="center">
      <strong>2</strong><br>
      <img src="https://github.com/De3vil/Faselhd/blob/main/scr/2.jpg" alt="Image 2" width="500">
    </td>
  </tr>
  <tr>
    <td align="center">
      <strong>3</strong><br>
      <img src="https://github.com/De3vil/Faselhd/blob/main/scr/3.jpg" alt="Image 3" width="500">
    </td>
    <td align="center">
      <strong>4</strong><br>
      <img src="https://github.com/De3vil/Faselhd/blob/main/scr/4.jpg" alt="Image 4" width="500">
    </td>
  </tr>
</table>

### Installation

#### Requirements
- **Python 3.10+** — Download [Python](https://www.python.org/downloads/)
- **OS:** Windows, Linux, or macOS

```bash
git clone https://github.com/De3vil/Faselhd.git
cd Faselhd
pip install -r requirements.txt
playwright install chromium
python nfshd.py
```

> **Note:** `playwright install chromium` downloads the Chromium browser needed for video stream extraction. This only needs to be done once. ffmpeg is downloaded automatically on first use.

***
<h4> Original Author — Abdulrahman Mohammed (De3vil) </h4>
  <a href="https://t.me/De3vil_3">
     <img src="https://img.shields.io/badge/De3vil_3-blue?style=for-the-badge&logo=Telegram&logoColor=00AEFF&labelColor=black&color=black">
  </a>
  <a href="https://www.facebook.com/De3vil.3">
     <img src="https://img.shields.io/badge/De3vil.3-blue?style=for-the-badge&logo=Facebook&logoColor=00AEFF&labelColor=black&color=black">
  </a>
  <a href="https://x.com/De3vil0">
     <img src="https://img.shields.io/badge/De3vil0-blue?style=for-the-badge&logo=x&logoColor=00AEFF&labelColor=black&color=black">
  </a>
  <br>

  If this tool has been useful for you, feel free to support the original author:
  <br>
  [![Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/De3vil)
  [![B De3vil](https://img.shields.io/badge/$-support-ff69b4.svg?style=flat)](https://www.paypal.com/paypalme/De3vil01)

***
<h4> Fork Maintainer — Abdo </h4>

  If you find this fork useful, consider supporting me:
  <br>
  <a href="https://ko-fi.com/abdobest">
    <img src="https://ko-fi.com/img/githubbutton_sm.svg">
  </a>
