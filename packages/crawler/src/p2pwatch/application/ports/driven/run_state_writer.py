"""``RunStateWriter``: whether the crawler's shutdown was requested."""

from abc import ABC, abstractmethod


class RunStateWriter(ABC):
    """Changes the run state from any thread: each call returns at once, its change follows."""

    @abstractmethod
    def set_shutdown_requested(self) -> None:
        """The crawler shuts down gracefully, and the container restarts it."""
