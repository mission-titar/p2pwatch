"""What the crawler expects from any client that reports its status; reachability is
``status()`` not raising ``ClientUnreachableError``. Stubs stay on ONE line."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

# Imported from here too until their importers move to the domain.
from p2pwatch.domain.status_reading import ChannelStatus as ChannelStatus
from p2pwatch.domain.status_reading import ClientStatus as ClientStatus
from p2pwatch.domain.status_reading import StatusReading as StatusReading
from p2pwatch.ports.driven.clock import MonotonicInstant


class StatusClient(Protocol):
    async def status(self) -> ClientStatus: ...


@dataclass(frozen=True)
class PublishedReading:
    reading: StatusReading
    published_at: MonotonicInstant


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
