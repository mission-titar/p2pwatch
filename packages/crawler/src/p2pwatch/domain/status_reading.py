"""A client's status, read every period: a reading stays fresh for two periods."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import HealthCondition, Threshold
from p2pwatch.domain.identifiers import Channel
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.value_bounds import require_well_formed_text

STATUS_PERIOD = timedelta(minutes=1)
READING_FRESH_FOR = 2 * STATUS_PERIOD


class ClientNotAnswering(DeclaredFailure):
    """A status reading aMule did not answer, a request it refused included."""


_UNANSWERED_IN_A_ROW = 3
CLIENT_UNREACHABLE = HealthCondition(
    name="unreachable",
    counts=ClientNotAnswering,
    fails_at=Threshold(failures=_UNANSWERED_IN_A_ROW, among_last=_UNANSWERED_IN_A_ROW),
    recovers_under=Threshold(failures=2, among_last=10),
)
# The readings come a minute apart, so the third unanswered one comes 2 minutes after the first.
UNREACHABLE_ALERT_AFTER = (_UNANSWERED_IN_A_ROW - 1) * STATUS_PERIOD


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
