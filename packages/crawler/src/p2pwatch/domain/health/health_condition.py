"""A health condition: one way a component can fail, judged on its latest outcomes."""

from dataclasses import dataclass
from enum import Enum
from typing import Self

from p2pwatch.domain.declared_failure import DeclaredFailure


@dataclass(kw_only=True, frozen=True)
class Outcome:
    """What one attempt gave: a success, or the failure it failed with."""

    reason: DeclaredFailure | None  # None for a success

    @classmethod
    def success(cls) -> Self:
        return cls(reason=None)

    @classmethod
    def failed(cls, reason: DeclaredFailure) -> Self:
        return cls(reason=reason)


class Health(Enum):
    UNKNOWN = "unknown"  # too few outcomes yet to tell
    HEALTHY = "healthy"
    FAILING = "failing"


@dataclass(kw_only=True, frozen=True)
class Threshold:
    """``failures`` failed outcomes among the latest ``among_last``."""

    failures: int
    among_last: int

    def __post_init__(self) -> None:
        if not 1 <= self.failures <= self.among_last:
            raise ValueError(f"{self}: from 1 failure to all of its outcomes expected")


@dataclass(kw_only=True, frozen=True)
class HealthCondition:
    """Failing once ``fails_at`` is met, healthy again once under ``recovers_under``, a stricter
    threshold so that a repeating pattern of failures does not alert again and again."""

    name: str
    counts: type[DeclaredFailure]  # the failure it counts: any other outcome is a success for it
    fails_at: Threshold
    recovers_under: Threshold

    def __post_init__(self) -> None:
        # Turning failing, its failures must still meet ``recovers_under``, or a success heals it.
        fails, recovers = self.fails_at, self.recovers_under
        if recovers.failures > fails.failures or recovers.among_last < fails.among_last:
            raise ValueError(f"{self.name!r} would recover on the failures that made it fail")

    @property
    def outcomes_kept(self) -> int:
        """How many latest outcomes it reads: the recovery's window, its longest."""
        return self.recovers_under.among_last

    def health_after(self, latest: tuple[Outcome, ...], *, previous: Health) -> Health:
        """The health ``latest`` outcomes give, newest last; ``previous`` is the health before."""
        if len(latest) < self.fails_at.among_last:
            return Health.UNKNOWN
        # While failing, it stays failing until under ``recovers_under``.
        threshold = self.recovers_under if previous is Health.FAILING else self.fails_at
        failures = sum(isinstance(o.reason, self.counts) for o in latest[-threshold.among_last :])
        return Health.FAILING if failures >= threshold.failures else Health.HEALTHY
