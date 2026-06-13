# Syncrotify

Syncrotify is an Electron desktop application for synchronizing a YouTube
Music playlist to:

- A local music folder
- A Rockbox-compatible MP3 player
- A supported stock iPod using the experimental iOpenPod adapter

The desktop UI is React and TypeScript. A bundled headless backend performs
playlist retrieval, media conversion, metadata tagging, device discovery, and
verified transfers.

## Requirements

- Node.js 22 or newer
- Python 3.11 or newer
- FFmpeg and FFprobe on `PATH`

## Development

```bash
npm install
python -m pip install -e ".[desktop-ipod]" pyinstaller
npm run dev
```

If the shell defines `ELECTRON_RUN_AS_NODE`, unset it before running Electron.

## Verification

```bash
npm run check
```

## Packaging

Windows:

```bash
npm run package:win
```

macOS:

```bash
npm run package:mac
```

Packaged artifacts are written to `release/`. The GitHub Actions workflow
builds Windows x64, macOS x64, and macOS arm64 artifacts on native runners.

## Data Safety

- Mirror deletion is limited to files tracked by Syncrotify manifests.
- A first device sync requires approval after a real plan is computed.
- Stock iPod database files are backed up before changes.
- Incomplete playlist retrieval prevents mirror deletions.

## License

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
