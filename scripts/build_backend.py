import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "resources" / "backend"
WORK = ROOT / "build" / "desktop-backend"
DIST = WORK / "dist"


def main() -> None:
    reset_directory(OUTPUT)
    reset_directory(DIST)
    WORK.mkdir(parents=True, exist_ok=True)
    name = "syncrotify-backend"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        name,
        "--onedir",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(DIST),
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
    built_directory = DIST / name
    if not built_directory.is_dir():
        raise FileNotFoundError(built_directory)
    shutil.copytree(built_directory, OUTPUT, dirs_exist_ok=True)

    executable = OUTPUT / (f"{name}.exe" if os.name == "nt" else name)
    if not executable.exists():
        raise FileNotFoundError(executable)
    smoke_test(executable)
    print(f"Built backend: {executable}")


def smoke_test(executable: Path) -> None:
    request = json.dumps(
        {
            "id": 1,
            "method": "app.bootstrap",
            "params": {"platform": sys.platform, "version": "build-smoke"},
        }
    )
    result = subprocess.run(
        [str(executable)],
        input=request + "\n",
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Backend smoke test exited with {result.returncode}: "
            f"{result.stderr.strip()}"
        )

    responses = [
        json.loads(line) for line in result.stdout.splitlines() if line.strip()
    ]
    if not any(item.get("id") == 1 and "result" in item for item in responses):
        raise RuntimeError(
            "Backend smoke test returned no bootstrap response: "
            f"{result.stdout.strip()}"
        )


def reset_directory(path: Path) -> None:
    resolved_root = ROOT.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise RuntimeError(f"Refusing to reset path outside repository: {resolved_path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def importable(module: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=ROOT,
        capture_output=True,
    )
    return result.returncode == 0


if __name__ == "__main__":
    main()
