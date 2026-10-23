from collections.abc import Mapping

from catalog_matching.domain.decision_tier import DecisionTier
from p2pwatch.application.ports.driven.coverage_reader import CoverageReader


class FakeCoverageReader(CoverageReader):
    def __init__(self, tiers_by_target: Mapping[str, tuple[DecisionTier, ...]]) -> None:
        self._tiers_by_target = tiers_by_target

    def read_target_coverage(self) -> Mapping[str, tuple[DecisionTier, ...]]:
        return self._tiers_by_target
