from p2pwatch.application.ports.driven.memory_releaser import MemoryReleaser


class FakeMemoryReleaser(MemoryReleaser):
    """Releases nothing; ``release_count`` counts its calls."""

    def __init__(self) -> None:
        self.release_count = 0

    def release(self) -> None:
        self.release_count += 1
