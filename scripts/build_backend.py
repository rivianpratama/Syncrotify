import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resources" / "backend"
WORK = ROOT / "build" / "desktop-backend"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    name = "syncrotify-backend"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        name,
        "--onefile",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(OUTPUT),
        "--workpath",
        str(WORK),
        "--specpath",
        str(WORK),
        "--collect-all",
        "yt_dlp",
        "--collect-all",
        "ytmusicapi",
        "--collect-all",
        "playwright",
        "--hidden-import",
        "iopenpod_bridge",
        "--hidden-import",
        "syncrotify_iopenpod",
        "--hidden-import",
        "syncrotify_backend.browser_auth",
        str(ROOT / "desktop_backend_entry.py"),
    ]

    if importable("SyncEngine"):
        for package in (
            "SyncEngine",
            "iTunesDB_Parser",
            "iTunesDB_Shared",
            "iTunesDB_Writer",
            "ArtworkDB_Parser",
            "ArtworkDB_Shared",
            "ArtworkDB_Writer",
            "SQLiteDB_Writer",
            "ipod_device",
        ):
            command.extend(["--collect-submodules", package])

    subprocess.run(command, cwd=ROOT, check=True)
    executable = OUTPUT / (f"{name}.exe" if os.name == "nt" else name)
    if not executable.exists():
        raise FileNotFoundError(executable)
    print(f"Built backend: {executable}")


def importable(module: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


if __name__ == "__main__":
    main()
