"""``RestartableBuilder``: builds a new object the node can restart at each call, such as a client
logged in to aMule."""

from abc import ABC, abstractmethod

from p2pwatch.application.ports.driven.restartable import Restartable


class RestartableBuilder[R: Restartable[object]](ABC):
    """Builds a new object of one kind at each call, such as a client logged in to aMule."""

    @abstractmethod
    def __str__(self) -> str:
        """The objects it builds as the log names them, such as ``client amuled``."""

    @abstractmethod
    async def build(self) -> R:
        """Builds a new object, its state and the works over it; one it could not finish holds
        nothing once the error is raised."""
