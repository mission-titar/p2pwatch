"""``RunStateReader``: whether the crawler searches or idles, and whether its shutdown was
requested."""

from abc import ABC, abstractmethod


class RunStateReader(ABC):
    """Reads the run state: its predicates from any thread, its waits on the crawler's loop only.

    The run state starts resumed, without a shutdown request.
    """

    @abstractmethod
    def is_paused(self) -> bool:
        """Whether the crawler idles."""

    @abstractmethod
    def is_shutdown_requested(self) -> bool:
        """Whether the crawler's graceful shutdown was requested."""

    @abstractmethod
    async def wait_until_resumed(self) -> None:
        """Returns once the crawler searches, at once if it does."""

    @abstractmethod
    async def wait_until_shutdown_requested(self) -> None:
        """Returns once the crawler's shutdown is requested, at once if it was."""
