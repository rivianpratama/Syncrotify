import os
import shutil
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "resources" / "bin"
ICON_DIR = ROOT / "resources" / "icons"


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
    deno = ROOT / "node_modules" / "deno-bin" / "bin" / deno_name
    if not deno.exists():
        raise FileNotFoundError("Install the deno-bin dev dependency before packaging")
    shutil.copy2(deno, BIN_DIR / deno_name)


if __name__ == "__main__":
    prepare_icons()
    prepare_binaries()
    print(f"Prepared desktop resources under {ROOT / 'resources'}")
