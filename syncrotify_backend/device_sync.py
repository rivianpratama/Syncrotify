import ctypes
import hashlib
import json
import os
import shutil
import string
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Iterable

from .tagging import get_video_id_from_file


AUDIO_EXTENSIONS = {".m4a", ".mp3", ".flac", ".opus", ".ogg", ".wav"}
MANAGED_DIR = ".syncrotify"
MANIFEST_NAME = "manifest.json"


@dataclass
class Device:
    id: str
    mode: str
    name: str
    model: str
    path: str
    connected: bool
    experimental: bool
    freeBytes: int
    totalBytes: int


@dataclass
class TransferPlan:
    add: list[str]
    update: list[str]
    remove: list[str]

    def summary(self, approved: bool, backup_required: bool) -> dict:
        return {
            "add": len(self.add),
            "update": len(self.update),
            "remove": len(self.remove),
            "requiresApproval": not approved,
            "backupRequired": backup_required,
        }


def _volume_candidates() -> Iterable[Path]:
    if os.name == "nt":
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for index, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << index):
                root = Path(f"{letter}:\\")
                drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(root))
                if drive_type in (2, 3):
                    yield root
        return

    if sys.platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.exists():
            yield from (path for path in volumes.iterdir() if path.is_dir())
        return

    for base in (Path("/media"), Path("/run/media"), Path("/mnt")):
        if base.exists():
            yield from (path for path in base.rglob("*") if path.is_dir())


def _device_id(root: Path) -> str:
    marker = root / MANAGED_DIR / "device.json"
    if marker.exists():
        try:
            value = json.loads(marker.read_text(encoding="utf-8")).get("id")
            if value:
                return str(value)
        except (OSError, json.JSONDecodeError):
            pass
    return hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]


def discover_devices() -> list[dict]:
    devices: list[Device] = []
    for root in _volume_candidates():
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue

        if (root / "iPod_Control").is_dir():
            devices.append(
                Device(
                    id=_device_id(root),
                    mode="ipod",
                    name=root.name or "iPod",
                    model="iPod Classic / Video",
                    path=str(root),
                    connected=True,
                    experimental=True,
                    freeBytes=usage.free,
                    totalBytes=usage.total,
                )
            )
        elif (root / ".rockbox").is_dir():
            devices.append(
                Device(
                    id=_device_id(root),
                    mode="rockbox",
                    name=root.name or "MP3 Player",
                    model="Rockbox-compatible MP3 player",
                    path=str(root),
                    connected=True,
                    experimental=False,
                    freeBytes=usage.free,
                    totalBytes=usage.total,
                )
            )
    return [asdict(device) for device in devices]


def eject_device(device_path: str) -> None:
    path = Path(device_path)
    if os.name == "nt":
        # Windows does not expose a reliable stdlib eject API. Flush writes and
        # let Explorer perform the hardware eject rather than pretending success.
        raise RuntimeError("Use Windows 'Safely Remove Hardware' to eject this device.")
    if sys.platform == "darwin":
        subprocess.run(["diskutil", "eject", str(path)], check=True, capture_output=True)
        return
    subprocess.run(["udisksctl", "unmount", "-b", str(path)], check=True, capture_output=True)


class ManagedMirror:
    def __init__(
        self,
        source: Path,
        destination: Path,
        policy: str,
        progress: Callable[[str, int, int, str], None],
        cancelled: Callable[[], bool],
    ):
        self.source = source
        self.destination = destination
        self.policy = policy
        self.progress = progress
        self.cancelled = cancelled
        self.managed_root = destination / MANAGED_DIR
        self.manifest_path = self.managed_root / MANIFEST_NAME

    def plan(self) -> TransferPlan:
        previous = self._load_manifest()
        current = self._source_manifest()
        add: list[str] = []
        update: list[str] = []

        for relative_path, metadata in current.items():
            old = previous.get(relative_path)
            destination = self.destination / relative_path
            if old is None or not destination.exists():
                add.append(relative_path)
            elif (
                old.get("size") != metadata["size"]
                or (
                    metadata.get("videoId")
                    and old.get("videoId") != metadata.get("videoId")
                )
            ):
                update.append(relative_path)

        remove = []
        if self.policy == "mirror":
            remove = [relative for relative in previous if relative not in current]
        return TransferPlan(add=add, update=update, remove=remove)

    def execute(self, plan: TransferPlan) -> None:
        current = self._source_manifest()
        required = sum(current[path]["size"] for path in [*plan.add, *plan.update])
        free = shutil.disk_usage(self.destination).free
        if required + 16 * 1024 * 1024 > free:
            raise RuntimeError("The destination does not have enough free space for this sync.")

        operations = [*plan.add, *plan.update]
        total = len(operations) + len(plan.remove)
        completed = 0
        for relative_path in operations:
            self._check_cancelled()
            source = self.source / relative_path
            destination = self.destination / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(f"{destination.suffix}.syncrotify-part")
            self._copy_verified(source, temporary)
            temporary.replace(destination)
            completed += 1
            self.progress("transfer", completed, total, f"Copied {source.name}")

        for relative_path in plan.remove:
            self._check_cancelled()
            target = self.destination / relative_path
            if target.exists() and self._is_within_destination(target):
                target.unlink()
            completed += 1
            self.progress("remove", completed, total, f"Removed {Path(relative_path).name}")

        self.managed_root.mkdir(parents=True, exist_ok=True)
        temporary_manifest = self.manifest_path.with_suffix(".json.tmp")
        temporary_manifest.write_text(
            json.dumps({"version": 1, "files": current}, indent=2),
            encoding="utf-8",
        )
        temporary_manifest.replace(self.manifest_path)

    def _source_manifest(self) -> dict[str, dict]:
        manifest: dict[str, dict] = {}
        if not self.source.exists():
            return manifest
        for path in self.source.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            stat = path.stat()
            relative = path.relative_to(self.source).as_posix()
            manifest[relative] = {
                "size": stat.st_size,
                "mtime": stat.st_mtime_ns,
                "videoId": get_video_id_from_file(path),
            }
        return manifest

    def _load_manifest(self) -> dict[str, dict]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8")).get("files", {})
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _copy_verified(source: Path, destination: Path) -> None:
        shutil.copy2(source, destination)
        if source.stat().st_size != destination.stat().st_size:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Verification failed while copying {source.name}")

    def _is_within_destination(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.destination.resolve())
            return True
        except ValueError:
            return False

    def _check_cancelled(self) -> None:
        if self.cancelled():
            raise InterruptedError("Sync cancelled")


class RockboxMirror(ManagedMirror):
    def __init__(
        self,
        source: Path,
        destination: Path,
        policy: str,
        progress: Callable[[str, int, int, str], None],
        cancelled: Callable[[], bool],
    ):
        self.device_root = destination
        super().__init__(
            source,
            destination / "Music" / "Syncrotify",
            policy,
            progress,
            cancelled,
        )
        self.managed_root = destination / MANAGED_DIR
        self.manifest_path = self.managed_root / MANIFEST_NAME

    def execute(self, plan: TransferPlan) -> None:
        self.destination.mkdir(parents=True, exist_ok=True)
        super().execute(plan)
        self._write_playlist(self.device_root)

    def _write_playlist(self, device_root: Path) -> None:
        playlist_dir = device_root / "Playlists"
        playlist_dir.mkdir(parents=True, exist_ok=True)
        entries = [
            "/" + path.relative_to(device_root).as_posix()
            for path in sorted((device_root / "Music" / "Syncrotify").rglob("*"))
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        ]
        temporary = playlist_dir / "Syncrotify.m3u8.tmp"
        temporary.write_text("\n".join(entries), encoding="utf-8-sig")
        temporary.replace(playlist_dir / "Syncrotify.m3u8")


class ExperimentalIPodMirror:
    def __init__(
        self,
        source: Path,
        destination: Path,
        policy: str,
        progress: Callable[[str, int, int, str], None],
        cancelled: Callable[[], bool],
        backup_root: Path,
    ):
        self.source = source
        self.destination = destination
        self.policy = policy
        self.progress = progress
        self.cancelled = cancelled
        self.backup_root = backup_root

    def plan(self) -> TransferPlan:
        bridge = self.destination / MANAGED_DIR / MANIFEST_NAME
        mirror = ManagedMirror(
            self.source,
            self.destination / MANAGED_DIR / "staged-library",
            self.policy,
            self.progress,
            self.cancelled,
        )
        mirror.manifest_path = bridge
        return mirror.plan()

    def execute(self, plan: TransferPlan) -> None:
        try:
            from syncrotify_iopenpod import sync_library
        except ImportError as error:
            raise RuntimeError(
                "The experimental iPod database adapter is not installed in this build."
            ) from error

        backup = self._backup_database()
        try:
            sync_library(
                source=self.source,
                device=self.destination,
                policy=self.policy,
                progress=self.progress,
                cancelled=self.cancelled,
            )
        except Exception:
            self._restore_database(backup)
            raise

    def _backup_database(self) -> Path:
        database_dir = self.destination / "iPod_Control" / "iTunes"
        if not database_dir.is_dir():
            raise RuntimeError("This volume does not contain a supported iPod database.")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = self.backup_root / f"ipod-{stamp}-{uuid.uuid4().hex[:8]}"
        backup.mkdir(parents=True, exist_ok=False)
        for filename in ("iTunesDB", "iTunesCDB", "Play Counts", "iTunesStats"):
            source = database_dir / filename
            if source.exists():
                shutil.copy2(source, backup / filename)
        return backup

    def _restore_database(self, backup: Path) -> None:
        database_dir = self.destination / "iPod_Control" / "iTunes"
        for source in backup.iterdir():
            shutil.copy2(source, database_dir / source.name)
