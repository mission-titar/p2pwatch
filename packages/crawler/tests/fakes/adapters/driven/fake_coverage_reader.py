from collections.abc import Mapping

from p2pwatch.application.ports.driven.coverage_reader import CoverageReader


class FakeCoverageReader(CoverageReader):
    def __init__(self, tiers_by_target: Mapping[str, tuple[str, ...]]) -> None:
        self._tiers_by_target = tiers_by_target

    def read_target_coverage(self) -> Mapping[str, tuple[str, ...]]:
        return self._tiers_by_target
