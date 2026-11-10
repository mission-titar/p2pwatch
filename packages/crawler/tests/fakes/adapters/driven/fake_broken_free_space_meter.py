from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError


class FakeBrokenFreeSpaceMeter(FreeSpaceMeter):
    """Cannot measure the output directory, as when its mount is missing."""

    def free_bytes(self) -> int:
        raise InaccessiblePathError("free space of /data/downloads unknown")
