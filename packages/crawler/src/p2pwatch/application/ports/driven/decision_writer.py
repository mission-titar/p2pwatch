"""``DecisionWriter``: appends the matcher's verdicts to the catalog, append-only (spec
data-model §4); synchronous, as every catalog port (spec data-model §3)."""

from abc import ABC, abstractmethod

from p2pwatch.domain.file_target_decision import DatedDecision, FileTargetDecision


class DecisionWriter(ABC):
    """Appends the matcher's verdicts on a file, per target."""

    @abstractmethod
    def record_decision(self, dated_decision: DatedDecision[FileTargetDecision]) -> None:
        """Appends ``dated_decision`` for its target; a retraction appends a ``retracted`` row
        (spec §7): the append-only table has no delete."""
