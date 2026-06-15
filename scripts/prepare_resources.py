import os
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "resources" / "bin"
ICON_DIR = ROOT / "resources" / "icons"
MIN_DENO_VERSION = (2, 3, 0)


def find_binary(name: str) -> Path:
    path = shutil.which(name)
    if path:
        return Path(path)
    raise FileNotFoundError(f"Required binary not found: {name}")


def prepare_icons() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    source = ROOT / "assets" / "icon.png"
    image = Image.open(source).convert("RGBA")
    image.save(
        ICON_DIR / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)],
    )
    shutil.copy2(source, ICON_DIR / "icon.png")
    if os.name != "nt":
        try:
            image.save(ICON_DIR / "icon.icns")
        except ValueError:
            pass


def prepare_binaries() -> None:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    for name in ("ffmpeg", "ffprobe"):
        source = find_binary(name)
        shutil.copy2(source, BIN_DIR / source.name)

    deno_name = "deno.exe" if os.name == "nt" else "deno"
    deno = ROOT / "node_modules" / "deno" / deno_name
    if not deno.exists():
        raise FileNotFoundError("Install the deno dev dependency before packaging")
    validate_deno_version(deno)
    shutil.copy2(deno, BIN_DIR / deno_name)


def validate_deno_version(deno: Path) -> None:
    result = subprocess.run(
        [str(deno), "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    match = re.search(r"^deno (\d+)\.(\d+)\.(\d+)", result.stdout)
    if not match:
        raise RuntimeError(f"Could not determine Deno version from: {result.stdout!r}")
    version = tuple(map(int, match.groups()))
    if version < MIN_DENO_VERSION:
        required = ".".join(map(str, MIN_DENO_VERSION))
        actual = ".".join(map(str, version))
        raise RuntimeError(f"Deno {actual} is unsupported; version {required}+ is required")


if __name__ == "__main__":
    prepare_icons()
    prepare_binaries()
    print(f"Prepared desktop resources under {ROOT / 'resources'}")
