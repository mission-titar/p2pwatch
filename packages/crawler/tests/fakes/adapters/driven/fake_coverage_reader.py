from collections.abc import Mapping

from p2pwatch.application.ports.driven.coverage_reader import CoverageReader
from p2pwatch.domain.matching.decision_tier import DecisionTier
from p2pwatch.domain.matching.identifiers import TargetId


class FakeCoverageReader(CoverageReader):
    def __init__(self, tiers_by_target: Mapping[TargetId, tuple[DecisionTier, ...]]) -> None:
        self._tiers_by_target = tiers_by_target

    def read_target_coverage(self) -> Mapping[TargetId, tuple[DecisionTier, ...]]:
        return self._tiers_by_target
