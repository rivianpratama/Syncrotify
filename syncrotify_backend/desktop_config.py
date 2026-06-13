import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "playlistUrl": "",
    "playlistName": "",
    "activeMode": "folder",
    "syncPolicy": "mirror",
    "closeBehavior": "tray",
    "launchAtLogin": False,
    "interval": 600,
    "smartStopThreshold": 5,
    "skipDurationThreshold": 2100,
    "maxRetries": 3,
    "audioFormat": "m4a",
    "audioQuality": "best",
    "filenameTemplate": "{artist} - {title}",
    "collisionStrategy": "smart_numbering",
    "sizeCheckEnabled": True,
    "maxDuplicates": 2,
    "pathTruncateLength": 60,
    "coverFormat": "JPEG",
    "coverWidth": 320,
    "coverHeight": 320,
    "coverQuality": 75,
    "embedLyrics": False,
    "stagingCacheEnabled": False,
    "destinations": {
        "folder": {
            "path": str(Path.home() / "Music" / "Syncrotify"),
            "deviceId": None,
            "displayName": "Music folder",
            "approved": False,
            "autoSync": False,
        },
        "rockbox": {
            "path": "",
            "deviceId": None,
            "displayName": "MP3 Player",
            "approved": False,
            "autoSync": True,
        },
        "ipod": {
            "path": "",
            "deviceId": None,
            "displayName": "iPod",
            "approved": False,
            "autoSync": True,
        },
    },
}


def user_data_path() -> Path:
    configured = os.environ.get("SYNCROTIFY_USER_DATA")
    if configured:
        return Path(configured)
    return Path.home() / ".syncrotify"


class DesktopConfig:
    def __init__(self, root: Path | None = None):
        self.root = root or user_data_path()
        self.path = self.root / "config.json"

    def load(self) -> dict[str, Any]:
        config = deepcopy(DEFAULT_CONFIG)
        if not self.path.exists():
            return config

        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return config

        for key, value in loaded.items():
            if key == "destinations" and isinstance(value, dict):
                for mode, destination in value.items():
                    if mode in config["destinations"] and isinstance(destination, dict):
                        config["destinations"][mode].update(destination)
            elif key in config:
                config[key] = value
        return config

    def save(self, config: dict[str, Any]) -> dict[str, Any]:
        validated = self._validate(config)
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(validated, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return validated

    def auth_dir(self) -> Path:
        path = self.root / "auth"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def staging_dir(self) -> Path:
        path = self.root / "staging"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _validate(config: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(DEFAULT_CONFIG)
        merged.update({key: value for key, value in config.items() if key != "destinations"})
        for mode in ("folder", "rockbox", "ipod"):
            destination = config.get("destinations", {}).get(mode, {})
            merged["destinations"][mode].update(destination)

        if merged["activeMode"] not in ("folder", "rockbox", "ipod"):
            raise ValueError("Unsupported destination mode")
        if merged["syncPolicy"] not in ("mirror", "additive"):
            raise ValueError("Unsupported sync policy")
        if merged["closeBehavior"] not in ("tray", "quit"):
            raise ValueError("Unsupported close behavior")
        if not 30 <= int(merged["interval"]) <= 86400:
            raise ValueError("Sync interval must be between 30 and 86400 seconds")
        if merged["audioFormat"] not in ("m4a", "mp3", "opus", "flac"):
            raise ValueError("Unsupported audio format")
        return merged
