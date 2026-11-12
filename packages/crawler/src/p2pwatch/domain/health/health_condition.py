"""A health condition: failures counted among a component's last outcomes, entering a band at one
threshold and leaving it under a stricter one (spec v5 lot 4, D9)."""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Self

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.outcome import TURNS, Bug, Outcome, OutcomeSource


class Health(Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"


def _require_count_within(count: int, *, of_last: int) -> None:
    if not 1 <= count <= of_last:
        raise ValueError(f"{count} among the last {of_last}: a count from 1 to its window expected")


@dataclass(kw_only=True, frozen=True)
class AtLeast:
    """A band's entry: at least ``count`` failures among the last ``of_last`` outcomes."""

    count: int
    of_last: int

    def __post_init__(self) -> None:
        _require_count_within(self.count, of_last=self.of_last)


@dataclass(kw_only=True, frozen=True)
class Below:
    """A band's exit: fewer than ``count`` failures among the last ``of_last`` outcomes."""

    count: int
    of_last: int

    def __post_init__(self) -> None:
        _require_count_within(self.count, of_last=self.of_last)


@dataclass(kw_only=True, frozen=True)
class Band:
    enters: AtLeast
    leaves: Below

    def __post_init__(self) -> None:
        # The entry's outcomes, still in the exit's window, must not satisfy the exit: no flapping.
        if self.leaves.count > self.enters.count or self.leaves.of_last < self.enters.of_last:
            raise ValueError(
                f"a band leaving below {self.leaves.count} among the last {self.leaves.of_last}"
                f" is not stricter than its entry at {self.enters.count}"
                f" among the last {self.enters.of_last}"
            )


# The starting values, tuned at the release candidate (spec v5 lot 4, appendix A, "Conditions").
_FAILING_BY_DEFAULT = Band(enters=AtLeast(count=3, of_last=3), leaves=Below(count=2, of_last=10))
_DEGRADED_BY_DEFAULT = Band(enters=AtLeast(count=2, of_last=10), leaves=Below(count=1, of_last=20))


@dataclass(kw_only=True, frozen=True)
class HealthCondition:
    """Counts the outcomes of ``source`` whose reason is a ``counting``; a success counts for it.
    It holds a band at least, ``failing`` or ``degraded``, both by default."""

    name: str
    source: OutcomeSource
    counting: type[DeclaredFailure | Bug]
    failing: Band | None = _FAILING_BY_DEFAULT
    degraded: Band | None = _DEGRADED_BY_DEFAULT

    def __post_init__(self) -> None:
        if not self.bands():
            raise ValueError(f"the condition {self.name!r}: a band at least expected")

    def bands(self) -> tuple[tuple[Health, Band], ...]:
        """Its bands, the worst first, each with the health it gives on entering it."""
        return tuple(
            (health, band)
            for health, band in ((Health.FAILING, self.failing), (Health.DEGRADED, self.degraded))
            if band is not None
        )


@dataclass(kw_only=True, frozen=True)
class ConditionWindow:
    """A condition's last outcomes and the health they gave, unknown until they fill its smallest
    entry."""

    condition: HealthCondition
    outcomes: tuple[Outcome, ...] = ()
    health: Health = Health.UNKNOWN

    def after(self, outcome: Outcome) -> Self:
        bands = self.condition.bands()
        kept = max(max(band.enters.of_last, band.leaves.of_last) for _, band in bands)
        outcomes = (*self.outcomes, outcome)[-kept:]
        if len(outcomes) < min(band.enters.of_last for _, band in bands):
            return replace(self, outcomes=outcomes, health=Health.UNKNOWN)
        return replace(self, outcomes=outcomes, health=self._judged(outcomes, bands=bands))

    def _judged(
        self, outcomes: tuple[Outcome, ...], *, bands: tuple[tuple[Health, Band], ...]
    ) -> Health:
        # Leaving a band, a milder one enters by its own entry only: an ended pattern then heals.
        for severity, band in bands:
            if self.health is severity:
                if self._failures(outcomes, of_last=band.leaves.of_last) >= band.leaves.count:
                    return severity
            elif self._failures(outcomes, of_last=band.enters.of_last) >= band.enters.count:
                return severity
        return Health.HEALTHY

    def _failures(self, outcomes: tuple[Outcome, ...], *, of_last: int) -> int:
        return sum(isinstance(o.reason, self.condition.counting) for o in outcomes[-of_last:])


BUGS = HealthCondition(name="bugs", source=TURNS, counting=Bug)
