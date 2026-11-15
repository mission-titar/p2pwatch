"""How a part's latest attempts decide its health."""

from dataclasses import dataclass
from enum import Enum


class HealthState(Enum):
    """A part's state of health, as one rule sees it."""

    UNKNOWN = "unknown"  # not enough attempts yet to tell
    HEALTHY = "healthy"
    FAILING = "failing"


@dataclass(kw_only=True, frozen=True)
class FailureThreshold:
    """A number of failures among the latest attempts, such as "2 of the last 10"."""

    failures: int
    among_last: int

    def __post_init__(self) -> None:
        if not 1 <= self.failures <= self.among_last:
            raise ValueError(f"{self}: needs from 1 failure to all of its attempts")


@dataclass(kw_only=True, frozen=True)
class HealthRule:
    """A rule judging a part's health from its latest attempts, such as "aMule does not answer":
    failing after 3 errors in a row, healthy again once fewer than 2 of the last 10 failed."""

    name: str
    counts: type[Exception]  # such as ClientError; failing with any other error counts as working
    fails_at: FailureThreshold
    recovers_under: FailureThreshold

    def __post_init__(self) -> None:
        # Otherwise the failures that just made it fail would let it recover at the next attempt.
        fails, recovers = self.fails_at, self.recovers_under
        if recovers.failures > fails.failures or recovers.among_last < fails.among_last:
            raise ValueError(f"{self.name!r} would recover on the failures that made it fail")

    @property
    def attempts_kept(self) -> int:
        """How many latest attempts it must remember: 10 for "fewer than 2 of the last 10"."""
        return self.recovers_under.among_last

    def state_after(self, latest_failed: tuple[bool, ...], *, previous: HealthState) -> HealthState:
        """The state once the newest attempt is counted: ``latest_failed`` says, for each latest
        attempt, oldest first, whether it failed with the error this rule counts."""
        if len(latest_failed) < self.fails_at.among_last:
            return HealthState.UNKNOWN
        # A failing part needs ``recovers_under`` to recover; any other needs ``fails_at`` to fail.
        threshold = self.recovers_under if previous is HealthState.FAILING else self.fails_at
        failures = sum(latest_failed[-threshold.among_last :])
        return HealthState.FAILING if failures >= threshold.failures else HealthState.HEALTHY
