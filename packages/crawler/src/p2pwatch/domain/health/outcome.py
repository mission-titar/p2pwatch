"""What one reading or one unit of work gave, and the source that records it."""

from dataclasses import dataclass
from typing import Self

from p2pwatch.domain.declared_failure import DeclaredFailure


@dataclass(kw_only=True, frozen=True)
class OutcomeSource:
    """What records an outcome: a condition reads one source, whose successes count for it."""

    name: str


@dataclass(kw_only=True, frozen=True)
class Outcome:
    reason: DeclaredFailure | None  # None for a success

    @classmethod
    def success(cls) -> Self:
        return cls(reason=None)

    @classmethod
    def declared(cls, reason: DeclaredFailure) -> Self:
        return cls(reason=reason)
