"""``RunStateReader``: whether the crawler's shutdown was requested."""

from abc import ABC, abstractmethod


class RunStateReader(ABC):
    """Reads the run state: its predicate from any thread, its wait on the crawler's loop only.

    The run state starts without a shutdown request.
    """

    @abstractmethod
    def is_shutdown_requested(self) -> bool:
        """Whether the crawler's graceful shutdown was requested."""

    @abstractmethod
    async def wait_until_shutdown_requested(self) -> None:
        """Returns once the crawler's shutdown is requested, at once if it was."""
