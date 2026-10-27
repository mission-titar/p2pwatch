from pathlib import Path


class FakeFreeBytes:
    """Measures the free bytes its test gives it, and keeps the directories it was asked about."""

    def __init__(self, free: int) -> None:
        self.free = free
        self.directories: list[Path] = []

    def free_bytes(self, directory: Path) -> int:
        self.directories.append(directory)
        return self.free
