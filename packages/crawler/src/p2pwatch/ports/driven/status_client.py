"""What the crawler expects from any client that reports its status."""

from abc import ABC, abstractmethod

from p2pwatch.domain.status_reading import ClientStatus


class StatusClient(ABC):
    """Reports the client's status."""

    @abstractmethod
    async def status(self) -> ClientStatus:
        """The client's status; reachability is this call not raising ``ClientUnreachableError``."""
