"""``RunStateReader``: whether the crawler searches or idles."""

from abc import ABC, abstractmethod


class RunStateReader(ABC):
    """Reads the run state: its predicates from any thread, its waits on the crawler's loop only."""

    @abstractmethod
    def is_paused(self) -> bool:
        """Whether the crawler idles."""

    @abstractmethod
    async def wait_until_resumed(self) -> None:
        """Returns once the crawler searches, at once if it does."""
