"""``CoverageReader``: reads what the targets' coverage is computed from."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.identifiers import TargetId


class CoverageReader(ABC):
    """Reads the catalog from any thread; a read that fails raises ``StoreError``."""

    @abstractmethod
    def read_target_coverage(self) -> Mapping[TargetId, tuple[DecisionTier, ...]]:
        """By ``target_id``, the tier of each file's latest decision for it, none retracted, the
        legacy retraction of no target left out."""
