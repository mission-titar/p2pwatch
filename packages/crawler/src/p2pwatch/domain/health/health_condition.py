"""How a part's latest attempts decide its health."""

from dataclasses import dataclass
from enum import Enum
from typing import Self

from p2pwatch.domain.declared_failure import DeclaredFailure


@dataclass(kw_only=True, frozen=True)
class Outcome:
    """Whether one attempt worked, and if not, why."""

    reason: DeclaredFailure | None  # None when it worked

    @classmethod
    def success(cls) -> Self:
        return cls(reason=None)

    @classmethod
    def failed(cls, reason: DeclaredFailure) -> Self:
        return cls(reason=reason)


class Health(Enum):
    """What a condition says of its part: unknown at first, then healthy or failing."""

    UNKNOWN = "unknown"  # not enough attempts yet to tell
    HEALTHY = "healthy"
    FAILING = "failing"


@dataclass(kw_only=True, frozen=True)
class Threshold:
    """A number of failures among the latest attempts, such as "2 of the last 10"."""

    failures: int
    among_last: int

    def __post_init__(self) -> None:
        if not 1 <= self.failures <= self.among_last:
            raise ValueError(f"{self}: needs from 1 failure to all of its attempts")


@dataclass(kw_only=True, frozen=True)
class HealthCondition:
    """One way a part can be unwell, such as "aMule does not answer": failing after 3 failures in a
    row, healthy again once fewer than 2 of the last 10 failed."""

    name: str
    counts: type[DeclaredFailure]  # such as ClientNotAnswering; any other outcome counts as working
    fails_at: Threshold
    recovers_under: Threshold

    def __post_init__(self) -> None:
        # Otherwise the failures that just made it fail would let it recover at the next attempt.
        fails, recovers = self.fails_at, self.recovers_under
        if recovers.failures > fails.failures or recovers.among_last < fails.among_last:
            raise ValueError(f"{self.name!r} would recover on the failures that made it fail")

    @property
    def outcomes_kept(self) -> int:
        """How many latest attempts it must remember: 10 for "fewer than 2 of the last 10"."""
        return self.recovers_under.among_last

    def health_after(self, latest: tuple[Outcome, ...], *, previous: Health) -> Health:
        """The health once the newest of ``latest`` is counted; ``previous`` is the one before."""
        if len(latest) < self.fails_at.among_last:
            return Health.UNKNOWN
        # A failing part needs ``recovers_under`` to recover; any other needs ``fails_at`` to fail.
        threshold = self.recovers_under if previous is Health.FAILING else self.fails_at
        failures = sum(isinstance(o.reason, self.counts) for o in latest[-threshold.among_last :])
        return Health.FAILING if failures >= threshold.failures else Health.HEALTHY
