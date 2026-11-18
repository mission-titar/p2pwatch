"""``Restartable``: an object holding state in memory that the node can restart, such as a client
logged in to aMule; its ``RestartableBuilder`` builds a new one at each restart."""

from abc import ABC, abstractmethod
from collections.abc import Sequence


class Restartable[W](ABC):
    """An object holding state in memory, such as a client logged in to aMule and the works ``W``
    over it: built whole, it never changes; a restart closes it and builds another."""

    @abstractmethod
    def works(self) -> Sequence[W]:
        """The works over its state, such as every search over the client's session."""

    @abstractmethod
    async def close(self) -> None:
        """Releases its state, such as the session with aMule logged out; a second close does
        nothing more."""
