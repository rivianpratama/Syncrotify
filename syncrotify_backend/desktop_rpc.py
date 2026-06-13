import json
import logging
import os
import shutil
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Callable

from .background import BackgroundMonitor
from .desktop_config import DesktopConfig
from .device_sync import (
    MANAGED_DIR,
    ExperimentalIPodMirror,
    ManagedMirror,
    RockboxMirror,
    discover_devices,
    eject_device,
)


def auto_sync_reason(
    config: dict[str, Any],
    previous_devices: list[dict[str, Any]],
    current_devices: list[dict[str, Any]],
    seconds_since_folder_sync: float,
) -> str | None:
    mode = config["activeMode"]
    destination = config["destinations"][mode]
    if not config["playlistUrl"] or not destination["path"] or not destination["autoSync"]:
        return None

    if mode == "folder":
        if seconds_since_folder_sync >= int(config["interval"]):
            return "interval"
        return None

    previous_ids = {device["id"] for device in previous_devices}
    return next(
        (
            "device"
            for device in current_devices
            if device["mode"] == mode
            and device["id"] == destination["deviceId"]
            and device["id"] not in previous_ids
        ),
        None,
    )


class RpcOutput:
    def __init__(self):
        self.lock = threading.Lock()

    def write(self, payload: dict[str, Any]) -> None:
        with self.lock:
            sys.stdout.write(json.dumps(payload, default=str) + "\n")
            sys.stdout.flush()

    def event(self, event: str, payload: Any) -> None:
        self.write({"event": event, "payload": payload})


class EventLogHandler(logging.Handler):
    def __init__(self, output: RpcOutput):
        super().__init__()
        self.output = output

    def emit(self, record: logging.LogRecord) -> None:
        level = "info"
        if record.levelno >= logging.ERROR:
            level = "error"
        elif record.levelno >= logging.WARNING:
            level = "warning"
        message = self.format(record)
        self.output.event(
            "activity",
            {
                "id": uuid.uuid4().hex,
                "timestamp": time.strftime("%H:%M:%S"),
                "level": level,
                "message": message,
            },
        )


class DesktopRuntime:
    def __init__(self, output: RpcOutput):
        self.output = output
        self.config_store = DesktopConfig()
        self.config = self.config_store.load()
        self.devices = discover_devices()
        self.activity: list[dict[str, Any]] = []
        self.progress = self._progress("idle", "Ready", "Waiting to sync", 0, 0, 0)
        self.sync_thread: threading.Thread | None = None
        self.sync_lock = threading.Lock()
        self.cancel_event = threading.Event()
        self.approval_event = threading.Event()
        self.pending_runner: Callable[[], None] | None = None
        self.last_folder_sync = time.monotonic()
        self.next_folder_sync_at = time.time() + int(self.config["interval"])

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.INFO)
        handler = EventLogHandler(output)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root_logger.addHandler(handler)
        threading.Thread(target=self._watch_for_auto_sync, daemon=True).start()

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "app.bootstrap": self.bootstrap,
            "config.save": self.save_config,
            "devices.refresh": self.refresh_devices,
            "devices.eject": self.eject,
            "sync.start": self.start_sync,
            "sync.stop": self.stop_sync,
            "sync.approve": self.approve_sync,
            "auth.login": self.login,
            "auth.import": self.import_auth,
            "auth.logout": self.logout,
        }
        if method not in handlers:
            raise ValueError(f"Unknown method: {method}")
        return handlers[method](params)

    def bootstrap(self, params: dict[str, Any]) -> dict[str, Any]:
        self.config = self.config_store.load()
        self.devices = discover_devices()
        return {
            "config": self.config,
            "devices": self.devices,
            "authConnected": self._auth_connected(),
            "progress": self.progress,
            "activity": self.activity[-200:],
            "nextAutoSyncAt": self._next_auto_sync_at(),
            "platform": params.get("platform", sys.platform),
            "version": params.get("version", "2.0.0"),
        }

    def save_config(self, params: dict[str, Any]) -> dict[str, Any]:
        self.config = self.config_store.save(params["config"])
        self._reset_folder_schedule()
        self._persist_device_identity()
        self.output.event("config", self.config)
        return self.config

    def refresh_devices(self, _params: dict[str, Any]) -> list[dict]:
        self.devices = discover_devices()
        self.output.event("devices", self.devices)
        return self.devices

    def eject(self, params: dict[str, Any]) -> None:
        device = next(
            (item for item in self.devices if item["id"] == params["deviceId"]),
            None,
        )
        if not device:
            raise ValueError("Device is no longer connected")
        eject_device(device["path"])

    def start_sync(self, _params: dict[str, Any]) -> dict[str, bool]:
        with self.sync_lock:
            if self.sync_thread and self.sync_thread.is_alive():
                return {"accepted": False}
            self.cancel_event.clear()
            self.approval_event.clear()
            self.sync_thread = threading.Thread(target=self._run_sync, daemon=True)
            if self.config["activeMode"] == "folder":
                self._reset_folder_schedule()
            self.sync_thread.start()
            return {"accepted": True}

    def stop_sync(self, _params: dict[str, Any]) -> None:
        self.cancel_event.set()
        self.approval_event.set()

    def approve_sync(self, _params: dict[str, Any]) -> None:
        self.approval_event.set()

    def login(self, _params: dict[str, Any]) -> dict[str, Any]:
        if self.sync_thread and self.sync_thread.is_alive():
            return {"started": False, "message": "Wait for the active sync to finish."}

        def run_login() -> None:
            try:
                from .browser_auth import extract_cookies

                success = extract_cookies(self.config_store.auth_dir())
                self.output.event("auth", {"connected": bool(success)})
            except Exception as error:
                self._activity("error", f"Authentication failed: {error}")
                self.output.event("auth", {"connected": False})

        threading.Thread(target=run_login, daemon=True).start()
        return {"started": True}

    def import_auth(self, params: dict[str, Any]) -> dict[str, bool]:
        source = Path(params["path"])
        if source.suffix.lower() == ".json":
            destination = self.config_store.auth_dir() / "headers_auth.json"
        else:
            destination = self.config_store.auth_dir() / "cookies.txt"
        shutil.copy2(source, destination)
        connected = self._auth_connected()
        self.output.event("auth", {"connected": connected})
        return {"connected": connected}

    def logout(self, _params: dict[str, Any]) -> None:
        for filename in ("headers_auth.json", "cookies.txt", "cookies.json"):
            (self.config_store.auth_dir() / filename).unlink(missing_ok=True)
        self.output.event("auth", {"connected": False})

    def _run_sync(self) -> None:
        plan_summary: dict[str, Any] | None = None
        try:
            self.config = self.config_store.load()
            mode = self.config["activeMode"]
            destination_config = self.config["destinations"][mode]
            destination = Path(destination_config["path"]) if destination_config["path"] else None
            if not self.config["playlistUrl"]:
                raise RuntimeError("Choose a YouTube Music playlist before syncing.")
            if destination is None:
                raise RuntimeError("Choose a destination before syncing.")
            if mode != "folder" and not destination.exists():
                self._set_progress("waiting", "Device disconnected", "Connect the configured device", 0, 0, 0)
                return

            staging = (
                destination
                if mode == "folder"
                else self.config_store.staging_dir() / mode / "library"
            )
            staging.mkdir(parents=True, exist_ok=True)

            self._set_progress("syncing", "Checking playlist", "Fetching playlist and metadata", 0, 5, 4)
            self._download_to(staging)
            self._check_cancelled()

            if mode != "folder":
                transfer = self._build_transfer(mode, staging, destination)
                plan = transfer.plan()
                plan_summary = plan.summary(destination_config["approved"], mode == "ipod")
                if not destination_config["approved"]:
                    self._set_progress(
                        "approval",
                        "Review first sync",
                        "Review the calculated changes, then approve this destination",
                        1,
                        5,
                        22,
                        plan=plan_summary,
                    )
                    self.approval_event.wait()
                    if self.cancel_event.is_set():
                        raise InterruptedError("Sync cancelled")
                    destination_config["approved"] = True
                    self.config = self.config_store.save(self.config)
                    plan_summary = plan.summary(True, mode == "ipod")
                self._set_progress(
                    "syncing",
                    "Preparing transfer",
                    "Comparing staged files with the destination",
                    1,
                    5,
                    22,
                    plan=plan_summary,
                )
                transfer.execute(plan)
                self._check_cancelled()
                self._set_progress(
                    "syncing",
                    "Verifying and cleaning cache",
                    "Removing files safely transferred to the device",
                    4,
                    5,
                    90,
                    plan=plan_summary,
                )
                if not self.config["stagingCacheEnabled"]:
                    self._clean_staging(staging)

            self._set_progress(
                "completed",
                "Sync complete",
                "Library is up to date",
                5,
                5,
                100,
                plan=plan_summary,
            )
            self._activity("success", "Sync completed successfully.")
        except InterruptedError:
            self._set_progress("cancelled", "Sync stopped", "No partial manifest was committed", 0, 0, 0)
            self._activity("warning", "Sync was cancelled.")
        except Exception as error:
            self._set_progress("failed", "Sync failed", str(error), 0, 0, 0)
            self._activity("error", str(error))
            traceback.print_exc(file=sys.stderr)

    def _watch_for_auto_sync(self) -> None:
        previous_devices = self.devices
        while True:
            time.sleep(2)
            try:
                current_devices = discover_devices()
                if current_devices != previous_devices:
                    self.devices = current_devices
                    self.output.event("devices", current_devices)

                self.config = self.config_store.load()
                reason = auto_sync_reason(
                    self.config,
                    previous_devices,
                    current_devices,
                    time.monotonic() - self.last_folder_sync,
                )
                if reason == "device":
                    self._refresh_paired_device_path(current_devices)
                if reason and self.start_sync({})["accepted"]:
                    message = (
                        "Configured device connected; automatic sync started."
                        if reason == "device"
                        else "Scheduled folder sync started."
                    )
                    self._activity("info", message)
                previous_devices = current_devices
            except Exception as error:
                self._activity("warning", f"Automatic sync check failed: {error}")

    def _persist_device_identity(self) -> None:
        mode = self.config["activeMode"]
        if mode == "folder":
            return
        destination = self.config["destinations"][mode]
        if not destination["path"] or not destination["deviceId"]:
            return
        marker = Path(destination["path"]) / MANAGED_DIR / "device.json"
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps({"id": destination["deviceId"]}, indent=2),
                encoding="utf-8",
            )
        except OSError as error:
            self._activity("warning", f"Could not persist device identity: {error}")

    def _refresh_paired_device_path(self, devices: list[dict[str, Any]]) -> None:
        mode = self.config["activeMode"]
        destination = self.config["destinations"][mode]
        device = next(
            (
                item
                for item in devices
                if item["mode"] == mode and item["id"] == destination["deviceId"]
            ),
            None,
        )
        if not device or destination["path"] == device["path"]:
            return
        destination["path"] = device["path"]
        destination["displayName"] = device["name"]
        self.config = self.config_store.save(self.config)
        self.output.event("config", self.config)

    def _reset_folder_schedule(self) -> None:
        self.last_folder_sync = time.monotonic()
        self.next_folder_sync_at = time.time() + int(self.config["interval"])
        self.output.event(
            "scheduler",
            {"nextAutoSyncAt": self._next_auto_sync_at()},
        )

    def _next_auto_sync_at(self) -> float | None:
        destination = self.config["destinations"]["folder"]
        if (
            self.config["activeMode"] == "folder"
            and destination["autoSync"]
            and self.config["playlistUrl"]
            and destination["path"]
        ):
            return self.next_folder_sync_at
        return None

    def _download_to(self, destination: Path) -> None:
        monitor = BackgroundMonitor()
        monitor.config_path = self.config_store.root / "engine_config.json"
        monitor.headers_path = self.config_store.auth_dir() / "headers_auth.json"
        monitor.cookies_txt_path = self.config_store.auth_dir() / "cookies.txt"
        monitor.config.update(
            {
                "playlist_url": self.config["playlistUrl"],
                "download_path": str(destination),
                "audio_format": self.config["audioFormat"],
                "audio_quality": self.config["audioQuality"],
                "filename_template": self.config["filenameTemplate"],
                "collision_strategy": self.config["collisionStrategy"],
                "size_check_enabled": self.config["sizeCheckEnabled"],
                "max_duplicates": self.config["maxDuplicates"],
                "path_truncate_length": self.config["pathTruncateLength"],
                "cover_width": self.config["coverWidth"],
                "cover_height": self.config["coverHeight"],
                "cover_format": self.config["coverFormat"],
                "cover_quality": self.config["coverQuality"],
                "embed_lyrics": self.config["embedLyrics"],
                "smart_stop_threshold": self.config["smartStopThreshold"],
                "skip_duration_threshold": self.config["skipDurationThreshold"],
                "max_retries": self.config["maxRetries"],
            }
        )
        monitor.process_playlist(mode="full")
        if not monitor.last_run_success:
            raise RuntimeError(
                "The source playlist could not be downloaded completely. "
                "No mirror deletions were applied."
            )

    def _build_transfer(self, mode: str, staging: Path, destination: Path):
        progress = lambda phase, current, total, message: self._set_progress(
            "syncing",
            phase.replace("_", " ").title(),
            message,
            current,
            max(total, 1),
            25 + int((current / max(total, 1)) * 60),
        )
        if mode == "rockbox":
            return RockboxMirror(
                staging,
                destination,
                self.config["syncPolicy"],
                progress,
                self.cancel_event.is_set,
            )
        if mode == "ipod":
            return ExperimentalIPodMirror(
                staging,
                destination,
                self.config["syncPolicy"],
                progress,
                self.cancel_event.is_set,
                self.config_store.root / "backups",
            )
        return ManagedMirror(
            staging,
            destination,
            self.config["syncPolicy"],
            progress,
            self.cancel_event.is_set,
        )

    def _clean_staging(self, staging: Path) -> None:
        for child in staging.iterdir():
            if child.name == "sync_manifest.json":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    def _check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise InterruptedError("Sync cancelled")

    def _auth_connected(self) -> bool:
        auth = self.config_store.auth_dir()
        return (auth / "headers_auth.json").exists() or (auth / "cookies.txt").exists()

    def _set_progress(
        self,
        status: str,
        phase: str,
        message: str,
        current: int,
        total: int,
        percent: int,
        plan: dict[str, Any] | None = None,
    ) -> None:
        self.progress = self._progress(status, phase, message, current, total, percent, plan)
        self.output.event("progress", self.progress)

    @staticmethod
    def _progress(
        status: str,
        phase: str,
        message: str,
        current: int,
        total: int,
        percent: int,
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "status": status,
            "phase": phase,
            "message": message,
            "current": current,
            "total": total,
            "percent": percent,
        }
        if plan is not None:
            payload["plan"] = plan
        return payload

    def _activity(self, level: str, message: str) -> None:
        event = {
            "id": uuid.uuid4().hex,
            "timestamp": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        }
        self.activity.append(event)
        self.activity = self.activity[-200:]
        self.output.event("activity", event)


def main() -> None:
    output = RpcOutput()
    runtime = DesktopRuntime(output)
    for raw_line in sys.stdin:
        try:
            request = json.loads(raw_line)
            result = runtime.dispatch(request["method"], request.get("params", {}))
            output.write({"id": request["id"], "result": result})
        except Exception as error:
            output.write(
                {
                    "id": request.get("id") if "request" in locals() else None,
                    "error": {
                        "code": -32000,
                        "message": str(error),
                    },
                }
            )
            traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
