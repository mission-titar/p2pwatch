"""A health condition: failures counted among a component's last outcomes, entering a band at one
threshold and leaving it under a stricter one (spec v5 lot 4, D9)."""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Self

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.outcome import Outcome, OutcomeSource


class Health(Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
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


@dataclass(kw_only=True, frozen=True)
class HealthCondition:
    """Counts the outcomes of ``source`` whose reason is a ``counting``; a success counts for it."""

    name: str
    source: OutcomeSource
    counting: type[DeclaredFailure]
    failing: Band


@dataclass(kw_only=True, frozen=True)
class ConditionWindow:
    """A condition's last outcomes and the health they gave, unknown until they fill its entry."""

    condition: HealthCondition
    outcomes: tuple[Outcome, ...] = ()
    health: Health = Health.UNKNOWN

    def after(self, outcome: Outcome) -> Self:
        band = self.condition.failing
        outcomes = (*self.outcomes, outcome)[-max(band.enters.of_last, band.leaves.of_last) :]
        if len(outcomes) < band.enters.of_last:
            health = Health.UNKNOWN
        elif self.health is Health.FAILING:
            leaves = self._failures(outcomes, of_last=band.leaves.of_last) < band.leaves.count
            health = Health.HEALTHY if leaves else Health.FAILING
        else:
            enters = self._failures(outcomes, of_last=band.enters.of_last) >= band.enters.count
            health = Health.FAILING if enters else Health.HEALTHY
        return replace(self, outcomes=outcomes, health=health)

    def _failures(self, outcomes: tuple[Outcome, ...], *, of_last: int) -> int:
        return sum(isinstance(o.reason, self.condition.counting) for o in outcomes[-of_last:])
