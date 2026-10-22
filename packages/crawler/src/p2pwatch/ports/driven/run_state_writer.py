"""``RunStateWriter``: whether the crawler searches or idles, and whether its shutdown was
requested."""

from abc import ABC, abstractmethod


class RunStateWriter(ABC):
    """Changes the run state from any thread: each call returns at once, its change follows."""

    @abstractmethod
    def pause(self) -> None:
        """Searches in flight finish, then the crawler idles."""

    @abstractmethod
    def resume(self) -> None:
        """The crawler searches again."""

    @abstractmethod
    def shut_down(self) -> None:
        """The crawler shuts down gracefully, and the container restarts it."""
