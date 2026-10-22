"""``ClaimCoverageChecker``: checks the claims are in bijection with what backs them."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimCoverageProblem:
    advisory_id: str
    message: str


@dataclass(frozen=True)
class ClaimCoverageReport:
    problems: tuple[ClaimCoverageProblem, ...]  # in the order of their advisory ids, then messages


class ClaimCoverageChecker(ABC):
    """Checks every claim of the VEX files is backed by one image premise or one source rule,
    with its justification, and that each of them backs a claim."""

    @abstractmethod
    def check_claim_coverage(self) -> ClaimCoverageReport:
        """The claims, image premises and source rules out of the bijection."""
