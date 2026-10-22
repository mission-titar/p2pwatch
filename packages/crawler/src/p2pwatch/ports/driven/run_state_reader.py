"""``RunStateReader``: whether the crawler searches or idles."""

from abc import ABC, abstractmethod


class RunStateReader(ABC):
    """Reads the run state from any thread."""

    @abstractmethod
    def is_paused(self) -> bool:
        """Whether the crawler idles."""
