"""How a part's latest checks decide its health."""

from dataclasses import dataclass
from enum import Enum


class HealthState(Enum):
    """A part's state of health, as one rule sees it."""

    UNKNOWN = "unknown"  # not enough checks yet to tell
    HEALTHY = "healthy"
    FAILING = "failing"


@dataclass(kw_only=True, frozen=True)
class Detections:
    """How many times a rule detected its case among its latest checks, such as "2 among the last
    10"."""

    times: int
    among_last: int

    def __post_init__(self) -> None:
        if not 1 <= self.times <= self.among_last:
            raise ValueError(f"{self}: needs from 1 detection to all of its checks")


@dataclass(kw_only=True, frozen=True)
class HealthRule:
    """A rule judging a part's health from its latest checks, such as "aMule does not answer":
    failing once detected 3 times in a row, healthy again once detected fewer than 2 times in 10."""

    name: str
    fails_at: Detections
    recovers_under: Detections

    def __post_init__(self) -> None:
        # Otherwise the detections that just made it fail would turn it healthy at the next check.
        fails, recovers = self.fails_at, self.recovers_under
        if recovers.times > fails.times or recovers.among_last < fails.among_last:
            raise ValueError(
                f"{self.name!r} would turn healthy on the detections that made it fail"
            )

    @property
    def checks_kept(self) -> int:
        """How many latest checks it must remember: 10 for "fewer than 2 times in the last 10"."""
        return self.recovers_under.among_last

    def state_after(
        self, latest_detected: tuple[bool, ...], *, previous: HealthState
    ) -> HealthState:
        """The state once the newest check is counted: ``latest_detected`` says, for each latest
        check, oldest first, whether the rule detected its case."""
        if len(latest_detected) < self.fails_at.among_last:
            return HealthState.UNKNOWN
        # A failing part turns healthy under ``recovers_under``; any other fails at ``fails_at``.
        threshold = self.recovers_under if previous is HealthState.FAILING else self.fails_at
        detections = sum(latest_detected[-threshold.among_last :])
        return HealthState.FAILING if detections >= threshold.times else HealthState.HEALTHY
