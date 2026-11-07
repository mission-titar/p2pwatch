"""The process's memory, injectable: ``MemoryReleaser`` hands what it freed back to the system."""

from abc import ABC, abstractmethod


class MemoryReleaser(ABC):
    """Hands back to the system the memory the process freed and its allocator keeps."""

    @abstractmethod
    def release(self) -> None:
        """Gives back what the allocator can, nothing where it cannot, and never raises."""
