"""``Work``: a task the node repeats, such as reading aMule's status every minute."""

from abc import ABC, abstractmethod


class Work(ABC):
    """A task the node repeats: a wait, then a turn, again; the first turn waits too, each work
    computing its wait from its own state. The supervisor takes the turns."""

    @abstractmethod
    def __str__(self) -> str:
        """The work as the log names it, such as ``status reading amuled``."""

    @abstractmethod
    async def wait_for_next_turn(self) -> None:
        """Returns once the next turn may start, at once if it already may."""

    @abstractmethod
    async def run_once(self) -> None:
        """Takes one turn, such as one reading of aMule's status."""
