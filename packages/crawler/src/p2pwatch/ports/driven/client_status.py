"""What the crawler expects from any client that reports its status; reachability is
``status()`` not raising ``ClientUnreachableError``. Stubs stay on ONE line."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from p2pwatch.ports.driven.clock import MonotonicInstant


@dataclass(frozen=True)
class ChannelStatus:
    """``connectable``: peers can connect to us; ``None`` when the client cannot tell."""

    channel: str
    connected: bool
    connectable: bool | None


@dataclass(frozen=True)
class ClientStatus:
    version: str | None
    channels: tuple[ChannelStatus, ...]


class StatusClient(Protocol):
    async def status(self) -> ClientStatus: ...


@dataclass(frozen=True)
class StatusReading:
    read_at: datetime  # for display: a reading's age is measured on the monotonic clock
    status: ClientStatus | None  # None: the client's API did not answer


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
