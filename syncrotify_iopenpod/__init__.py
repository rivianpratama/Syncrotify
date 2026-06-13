"""Optional stock-iPod bridge.

The Electron release packages the pinned iOpenPod engine next to this module.
Keeping the adapter separate prevents its alpha database writer from affecting
folder or Rockbox synchronization.
"""

from pathlib import Path
from typing import Callable


def sync_library(
    source: Path,
    device: Path,
    policy: str,
    progress: Callable[[str, int, int, str], None],
    cancelled: Callable[[], bool],
) -> None:
    try:
        from iopenpod_bridge import sync_library as bridge_sync
    except ImportError as error:
        raise RuntimeError(
            "Stock iPod support requires the pinned iOpenPod bridge included in packaged builds."
        ) from error
    bridge_sync(
        source=source,
        device=device,
        policy=policy,
        progress=progress,
        cancelled=cancelled,
    )
