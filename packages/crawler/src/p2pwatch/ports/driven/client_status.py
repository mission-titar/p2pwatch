"""What the crawler expects from any client that reports its status, and the board of the
latest readings."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import ClientStatus, PublishedReading, StatusReading


class StatusClient(ABC):
    """Reports the client's status."""

    @abstractmethod
    async def status(self) -> ClientStatus:
        """The client's status; reachability is this call not raising ``ClientUnreachableError``."""


class ClientStatusWriter(ABC):
    """Publishes each client's latest status reading, from its status loop."""

    @abstractmethod
    def publish(
        self, client_name: str, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        """Replaces the client's reading."""


class ClientStatusReader(ABC):
    """Reads each client's latest status reading, from any thread."""

    @abstractmethod
    def read_readings(self) -> Mapping[str, PublishedReading | None]:
        """Each client's reading, ``None`` before its first."""
