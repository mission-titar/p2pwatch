"""``ShutilFreeSpaceMeter``: ``FreeSpaceMeter`` over ``shutil.disk_usage`` (one ``statvfs``)."""

from pathlib import Path
from shutil import disk_usage

from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError


class ShutilFreeSpaceMeter(FreeSpaceMeter):
    """Free bytes of the filesystem holding ``path``. No file is opened, no tree is walked."""

    def __init__(self, path: Path | str) -> None:
        self._path = path

    def free_bytes(self) -> int:
        try:
            return disk_usage(self._path).free
        except OSError as error:
            raise InaccessiblePathError(
                f"free space of {self._path} unknown: {error.strerror}"
            ) from error
