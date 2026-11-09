"""``DecisionWriter``: appends the matcher's verdicts to the catalog, append-only (spec
data-model §4); synchronous, as every catalog port (spec data-model §3)."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from p2pwatch.domain.file_target_decision import DatedDecision, FileTargetDecision


class DecisionWriter(ABC):
    """Appends the matcher's verdicts on a file, per target."""

    @abstractmethod
    def record_decisions(
        self, dated_decisions: Sequence[DatedDecision[FileTargetDecision]]
    ) -> None:
        """Appends ``dated_decisions`` in one transaction, a retraction as a ``retracted`` row
        (spec §7); a ``StoreError``, a file never observed's included, writes none of them."""
