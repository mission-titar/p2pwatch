"""A client's status, read every period: a reading stays fresh for two periods, and the conditions
its readings feed count them at the entry of the alerts they replace (spec v5 lot 4, D21)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import AtLeast, Band, Below, HealthCondition
from p2pwatch.domain.health.outcome import OutcomeSource
from p2pwatch.domain.identifiers import Channel
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.value_bounds import require_well_formed_text

STATUS_PERIOD = timedelta(minutes=1)
READING_FRESH_FOR = 2 * STATUS_PERIOD


class ClientNotAnswering(DeclaredFailure):
    """A reading the client's API did not answer, a refused route included: a reason, never
    raised."""


STATUS_API_ANSWER = OutcomeSource(name="the status reading's API answer")
CLIENT_UNREACHABLE = HealthCondition(
    name="unreachable",
    source=STATUS_API_ANSWER,
    counting=ClientNotAnswering,
    failing=Band(enters=AtLeast(count=3, of_last=3), leaves=Below(count=2, of_last=10)),
)


def lasting_at_entry(condition: HealthCondition) -> timedelta:
    """How long a reading condition has held on entering failing: a period per later reading."""
    return (condition.failing.enters.count - 1) * STATUS_PERIOD


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

    def __post_init__(self) -> None:
        require_well_formed_text(self.version, error_label="a client status's version")


@dataclass(kw_only=True, frozen=True)
class StatusReading:
    read_at: datetime  # for display: a reading's age is measured on the monotonic clock
    status: ClientStatus | None  # None: the client's API did not answer


@dataclass(kw_only=True, frozen=True)
class PublishedReading:
    reading: StatusReading
    published_at: MonotonicInstant
