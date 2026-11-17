"""``Restartable``: an object holding state in memory that the node can rebuild, such as the aMule
client and its session."""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class Restartable[W](ABC):
    """An object holding state in memory, such as the aMule client and its session with aMule: a
    rebuild builds that state anew, and hands back the works ``W`` to run over it."""

    @abstractmethod
    def __str__(self) -> str:
        """The object as the log names it, such as ``client amuled``."""

    @abstractmethod
    async def rebuild(self) -> Sequence[W]:
        """Builds its state anew, such as a new session with aMule, and returns the works over it;
        the works over the old state are stopped before."""
