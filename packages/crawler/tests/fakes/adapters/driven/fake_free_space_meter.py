from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter


class FakeFreeSpaceMeter(FreeSpaceMeter):
    """Measures the free bytes it is given."""

    def __init__(self, free: int) -> None:
        self.free = free

    def free_bytes(self) -> int:
        return self.free
