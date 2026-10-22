"""``ShutilFreeSpaceMeter``: ``FreeSpaceMeter`` over ``shutil.disk_usage`` (one ``statvfs``)."""

from pathlib import Path
from shutil import disk_usage

from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter


class ShutilFreeSpaceMeter(FreeSpaceMeter):
    """Free bytes of the filesystem holding ``path``. No file is opened, no tree is walked."""

    def __init__(self, path: Path | str) -> None:
        self._path = path

    def free_bytes(self) -> int:
        return disk_usage(self._path).free
