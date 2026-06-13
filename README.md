<div align="center">
  <img src="assets/icon.png" width="120" height="120" alt="Syncrotify Logo" />
  <h1>Syncrotify</h1>
  <p><strong>Auto-sync Youtube Music playlist into MP3 Player and iPod.</strong></p>

  <p>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/rivianpratama/Syncrotify?style=for-the-badge&color=blue" alt="License"/></a>
    <a href="https://github.com/rivianpratama/Syncrotify/releases"><img src="https://img.shields.io/github/v/release/rivianpratama/Syncrotify?style=for-the-badge&color=purple" alt="Release"/></a>
    <a href="https://github.com/rivianpratama/Syncrotify/actions"><img src="https://img.shields.io/github/actions/workflow/status/rivianpratama/Syncrotify/desktop-build.yml?style=for-the-badge&label=Build" alt="Build Status"/></a>
  </p>

  <p>
    <a href="#-features">Features</a> •
    <a href="#-architecture">Architecture</a> •
    <a href="#-prerequisites">Prerequisites</a> •
    <a href="#-development-setup">Development Setup</a> •
    <a href="#-packaging--building">Packaging & Building</a> •
    <a href="#-data-safety-principles">Data Safety</a>
  </p>
</div>

<hr />

Syncrotify is an Electron-based desktop application designed to sync your YouTube Music playlists directly to local storage, Rockbox-compatible MP3 players, and stock iPods. 

By utilizing an Electron (React + TypeScript) user interface and a headless Python synchronization engine, Syncrotify delivers a seamless and reliable offline music experience.

---

### 🌟 Features

*   🔄 **YouTube Music Synchronization**
    *   Seamless playlist retrieval with automated token management.
    *   Support for public, unlisted, and private user playlists.
*   📂 **Local Mirroring**
    *   Keep any local music directory exactly mirroring your cloud playlists.
*   🎧 **Legacy & Alternative Device Integration**
    *   **Rockbox Support:** Sync tracks to target devices running Rockbox alternative firmware.
    *   **Stock Apple iPod Support:** Experimental integration with stock iPod databases via a pinned, customized [iOpenPod](https://github.com/TheRealSavi/iOpenPod) adapter.
*   🏷️ **Automatic Metadata & Tagging**
    *   Integrates with MusicBrainz for high-fidelity track identification and tagging.
    *   Applies correct ID3/Vorbis tags and embeds high-resolution album artwork using `mutagen` and `mediafile`.
*   🛡️ **Data Safety Priority**
    *   Protections against database corruption, accidental deletions, and incomplete playlist synchronizations.

---

### 🏗️ Architecture

Syncrotify separates concerns by keeping the user interface lightweight and doing all heavy-duty network and I/O tasks in a headless Python backend.

```
┌──────────────────────────────────────┐
│        Electron Shell (React)        │ <── Frontend UI (TypeScript, Vite)
└──────────────────────────────────────┘
                   │
                   │ IPC (Inter-Process Communication / JSON-RPC)
                   ▼
┌──────────────────────────────────────┐
│    Python Backend (Headless RPC)     │ <── Media Sync Engine
└──────────────────────────────────────┘
   ├── yt-dlp / ytmusicapi  (Media Downloaders)
   ├── MusicBrainz / Mutagen (Metadata & Tagging)
   └── iOpenPod Bridge      (iPod Database IO Engine)
```

---

### 📋 Prerequisites

Ensure you have the following dependencies installed on your system:

*   **Node.js** `22.x` or newer
*   **Python** `3.11.x` or newer
*   **FFmpeg** & **FFprobe** (Must be available in your system `PATH`)

---

### 🚀 Development Setup

Follow these steps to set up and run the application locally:

#### 1. Clone the Repository
```bash
git clone https://github.com/rivianpratama/Syncrotify.git
cd Syncrotify
```

#### 2. Install Node.js Dependencies
```bash
npm install
```

#### 3. Setup Python Virtual Environment & Install Dependencies
Create a virtual environment, activate it, and install dependencies along with `pyinstaller` for building:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate

# Install dependencies in editable mode
python -m pip install -e ".[desktop-ipod]" pyinstaller
```

#### 4. Run the Development Server
Launch both the frontend and background backend process concurrently:
```bash
npm run dev
```
> [!NOTE]
> If your current shell environment defines `ELECTRON_RUN_AS_NODE`, unset it before launching.
> *   Windows (PowerShell): `$env:ELECTRON_RUN_AS_NODE=""`
> *   macOS/Linux: `unset ELECTRON_RUN_AS_NODE`

#### 5. Verify & Run Test Suite
Run vitest frontend tests and python backend unit tests to ensure everything functions properly:
```bash
npm run check
```

---

### 📦 Packaging & Building

Packaging Syncrotify compiles the React frontend, builds the headless Python backend into a standalone executable using PyInstaller, and bundles the application using Electron Builder.

#### Windows (NSIS Installer & Portable Executable)
```bash
npm run package:win
```

#### macOS (DMG & Zip Installer)
```bash
npm run package:mac
```

All built artifacts will be located under the `release/` directory.

---

### 🛡️ Data Safety Principles

To protect your personal music collection and connected legacy hardware, Syncrotify enforces several safety invariants:

*   🚫 **Restricted Deletions:** Syncrotify tracks every file it creates via sync manifests. Mirror deletions are restricted *only* to files that Syncrotify itself has synced.
*   📝 **Interactive Approval:** A full dry-run plan is computed first. No writes or file transfers begin until you explicitly approve the sync plan.
*   💾 **Automatic Backups:** The stock iPod iTunes database file is backed up before any write operations occur to prevent loss or database corruption.
*   📡 **Safe Failures:** If playlist retrieval is incomplete or interrupted by network issues, Syncrotify aborts the process and will refuse to perform mirror deletions.

---

### 🤝 Credits & Acknowledgements

*   **[shira](https://github.com/KraXen72/shira)** by [KraXen72](https://github.com/KraXen72) – Inspiration and core design patterns for the YouTube downloader and synchronization pipeline.
*   **[iOpenPod](https://github.com/TheRealSavi/iOpenPod)** by [TheRealSavi](https://github.com/TheRealSavi) – Pinned library powering the database write-and-sync synchronization engine for stock iPods.

---

### 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for more details.

