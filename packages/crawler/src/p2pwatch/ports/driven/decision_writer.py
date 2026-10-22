"""``DecisionWriter``: appends the matcher's verdicts to the catalog, append-only (spec
data-model §4); synchronous, as every catalog port (spec data-model §3)."""

from abc import ABC, abstractmethod
from datetime import datetime

from catalog_matching.domain.engine import MatchDecision
from p2pwatch.domain.file_key import FileKey


class DecisionWriter(ABC):
    """Appends the matcher's verdicts on a file, per target."""

    @abstractmethod
    def record_decision(
        self, file: FileKey, decision: MatchDecision, decided_at: datetime, node_id: str
    ) -> None:
        """Appends ``decision`` for its target."""

    @abstractmethod
    def record_retraction(
        self, file: FileKey, target_id: str, decided_at: datetime, node_id: str
    ) -> None:
        """Appends a ``retracted`` row (spec §7): the append-only table has no delete."""
