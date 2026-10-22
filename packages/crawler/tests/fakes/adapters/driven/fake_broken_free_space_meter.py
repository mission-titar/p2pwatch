from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter


class FakeBrokenFreeSpaceMeter(FreeSpaceMeter):
    """Cannot measure the output directory, as when its mount is missing."""

    def free_bytes(self) -> int:
        raise FileNotFoundError("/data/downloads")
