from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter


class FakeFreeSpaceMeter(FreeSpaceMeter):
    """Scripted free space (the real adapter calls shutil.disk_usage)."""

    def __init__(self, free: int) -> None:
        self.free = free

    def free_bytes(self) -> int:
        return self.free
