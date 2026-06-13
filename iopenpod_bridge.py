"""Headless bridge to the pinned iOpenPod sync engine.

This module deliberately avoids iOpenPod's GUI and acoustic-fingerprint
workflow. Syncrotify already embeds stable YouTube video IDs in each staged
track, so those IDs become the managed mapping keys. This keeps exact-mirror
deletions limited to tracks previously written by Syncrotify.
"""

from pathlib import Path
from typing import Callable

from syncrotify_backend.tagging import get_video_id_from_file


def _mapping_key(video_id: str) -> str:
    return f"syncrotify:youtube:{video_id}"


def sync_library(
    source: Path,
    device: Path,
    policy: str,
    progress: Callable[[str, int, int, str], None],
    cancelled: Callable[[], bool],
) -> None:
    from SyncEngine._db_io import read_existing_database
    from SyncEngine.contracts import SyncAction, SyncItem, SyncPlan, SyncRequest
    from SyncEngine.mapping import MappingManager
    from SyncEngine.pc_library import PCLibrary
    from SyncEngine.sync_executor import SyncExecutor

    library = PCLibrary(str(source))
    tracks = list(
        library.scan(
            include_video=False,
            progress_callback=lambda current, total, name: progress(
                "scan", current, total, f"Reading {name}"
            ),
            is_cancelled=cancelled,
        )
    )
    if cancelled():
        raise InterruptedError("Sync cancelled")

    source_tracks: dict[str, object] = {}
    for track in tracks:
        video_id = get_video_id_from_file(Path(track.path))
        if video_id:
            source_tracks[_mapping_key(video_id)] = track

    if not source_tracks and tracks:
        raise RuntimeError(
            "Staged tracks do not contain Syncrotify video IDs; refusing an iPod database write."
        )

    database = read_existing_database(device)
    ipod_tracks = database.get("tracks", [])
    ipod_by_id = {
        int(track.get("db_track_id", track.get("db_id", 0)) or 0): track
        for track in ipod_tracks
    }
    mapping_manager = MappingManager(device)
    mapping = mapping_manager.load()
    plan = SyncPlan()

    for fingerprint, track in source_tracks.items():
        entries = mapping.get_entries(fingerprint)
        existing = next(
            (entry for entry in entries if entry.db_track_id in ipod_by_id),
            None,
        )
        if existing is None:
            plan.to_add.append(
                SyncItem(
                    action=SyncAction.ADD_TO_IPOD,
                    fingerprint=fingerprint,
                    pc_track=track,
                    estimated_size=track.size,
                    description=f"Add {track.artist} - {track.title}",
                )
            )
            continue

        source_stat = Path(track.path).stat()
        if (
            source_stat.st_size != existing.source_size
            or source_stat.st_mtime != existing.source_mtime
        ):
            plan.to_update_file.append(
                SyncItem(
                    action=SyncAction.UPDATE_FILE,
                    fingerprint=fingerprint,
                    pc_track=track,
                    db_track_id=existing.db_track_id,
                    ipod_track=ipod_by_id[existing.db_track_id],
                    estimated_size=track.size,
                    description=f"Update {track.artist} - {track.title}",
                )
            )

    if policy == "mirror":
        for fingerprint, entries in mapping.tracks.items():
            if not fingerprint.startswith("syncrotify:youtube:"):
                continue
            if fingerprint in source_tracks:
                continue
            for entry in entries:
                ipod_track = ipod_by_id.get(entry.db_track_id)
                if not ipod_track:
                    continue
                plan.to_remove.append(
                    SyncItem(
                        action=SyncAction.REMOVE_FROM_IPOD,
                        fingerprint=fingerprint,
                        db_track_id=entry.db_track_id,
                        ipod_track=ipod_track,
                        description=f"Remove {ipod_track.get('Title', 'managed track')}",
                    )
                )

    total = len(plan.to_add) + len(plan.to_update_file) + len(plan.to_remove)
    progress("database", 0, max(total, 1), "Preparing iPod database update")

    def report(update) -> None:
        message = update.message or update.stage.replace("_", " ").title()
        progress(update.stage, update.current, max(update.total, 1), message)

    result = SyncExecutor(
        device,
        cache_dir=source.parent / "iopenpod-cache",
        max_device_write_workers=1,
    ).execute_request(
        SyncRequest(
            plan=plan,
            mapping=mapping,
            progress_callback=report,
            is_cancelled=cancelled,
        )
    )
    if not result.success:
        detail = result.errors[0][1] if result.errors else "Unknown iPod database error"
        raise RuntimeError(detail)
