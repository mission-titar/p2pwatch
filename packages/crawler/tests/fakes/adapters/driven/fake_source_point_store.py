from collections.abc import Sequence
from datetime import datetime

from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.source import LatestPoint, SourceKey, SourcePoint, SourceReading
from p2pwatch.domain.store_error import StoreError


class FakeSourcePointStore(SourcePointWriter, SourcePointReader):
    """Keeps each point ``record_points`` writes in ``recorded``; raises ``StoreError`` for a
    point of a hash in ``fail_for``. ``latest`` answers ``read_latest_point``, each call noted in
    ``latest_asked``; ``history`` answers ``read_earlier_points`` per source, no point by default,
    and ``baseline`` answers ``has_points_before``, each call noted in ``baselines``, the first
    ``baseline_failures`` raising ``StoreError``."""

    def __init__(
        self,
        *,
        fail_for: set[str] | None = None,
        latest: LatestPoint | None = None,
        history: dict[SourceKey, tuple[LatestPoint, ...]] | None = None,
        baseline: bool = True,
        baseline_failures: int = 0,
    ) -> None:
        self.recorded: list[SourcePoint] = []
        self.latest_asked: list[tuple[str, SourceReading, datetime, datetime]] = []
        self.asked: list[tuple[SourceKey, datetime]] = []
        self.baselines: list[datetime] = []
        self.node_ids: set[NodeId] = set()  # every read's and every point's
        self._fail_for = fail_for or set()
        self._latest = latest
        self._history = history or {}
        self._baseline = baseline
        self._baseline_failures = baseline_failures

    def record_points(self, points: Sequence[SourcePoint]) -> None:
        self.node_ids.update(point.node_id for point in points)
        if any(point.file.native_id in self._fail_for for point in points):
            raise StoreError("record_points failed")
        self.recorded += points

    def read_latest_point(
        self,
        file: FileKey,
        *,
        reading: SourceReading,
        since: datetime,
        before: datetime,
        node_id: NodeId,
    ) -> LatestPoint | None:
        self.node_ids.add(node_id)
        self.latest_asked.append((file.native_id, reading, since, before))
        return self._latest

    def read_earlier_points(
        self, source: SourceKey, *, before: datetime, node_id: NodeId
    ) -> tuple[LatestPoint, ...]:
        self.node_ids.add(node_id)
        self.asked.append((source, before))
        return self._history.get(source, ())

    def has_points_before(self, before: datetime, *, node_id: NodeId) -> bool:
        self.node_ids.add(node_id)
        self.baselines.append(before)
        if len(self.baselines) <= self._baseline_failures:
            raise StoreError("has_points_before failed")
        return self._baseline
