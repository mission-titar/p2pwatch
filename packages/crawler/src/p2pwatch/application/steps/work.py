"""``Work``: what the supervisor runs again and again, one turn a call to ``run_once()``."""

from abc import ABC, abstractmethod


class Work(ABC):
    """A turn and the wait before it, the first included, computed from the work's own state."""

    @abstractmethod
    def __str__(self) -> str:
        """The work as the supervisor's log lines name it."""

    @abstractmethod
    async def run_once(self) -> None:
        """Takes one turn."""

    @abstractmethod
    async def wait_for_next_turn(self) -> None:
        """Returns once the next turn may start."""
