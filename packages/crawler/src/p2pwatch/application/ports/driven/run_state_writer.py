"""``RunStateWriter``: whether the crawler searches or idles, and whether its shutdown was
requested."""

from abc import ABC, abstractmethod


class RunStateWriter(ABC):
    """Changes the run state from any thread: each call returns at once, its change follows."""

    @abstractmethod
    def set_paused(self, paused: bool) -> None:
        """Paused, searches in flight finish, then the crawler idles; else it searches again."""

    @abstractmethod
    def set_shutdown_requested(self) -> None:
        """The crawler shuts down gracefully, and the container restarts it."""
