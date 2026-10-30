"""A client's status, read every period: a reading stays fresh for two periods."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from p2pwatch.domain.identifiers import Channel
from p2pwatch.domain.monotonic_instant import MonotonicInstant

STATUS_PERIOD = timedelta(minutes=1)
READING_FRESH_FOR = 2 * STATUS_PERIOD


def is_reading_fresh(age: timedelta) -> bool:
    """Whether a reading this old still shows the client's status; its age is monotonic."""
    return age <= READING_FRESH_FOR


@dataclass(kw_only=True, frozen=True)
class ChannelStatus:
    """``connectable``: peers can connect to us; ``None`` when the client cannot tell."""

    channel: Channel
    connected: bool
    connectable: bool | None


@dataclass(kw_only=True, frozen=True)
class ClientStatus:
    version: str | None
    channels: tuple[ChannelStatus, ...]


@dataclass(kw_only=True, frozen=True)
class StatusReading:
    read_at: datetime  # for display: a reading's age is measured on the monotonic clock
    status: ClientStatus | None  # None: the client's API did not answer


@dataclass(kw_only=True, frozen=True)
class PublishedReading:
    reading: StatusReading
    published_at: MonotonicInstant
