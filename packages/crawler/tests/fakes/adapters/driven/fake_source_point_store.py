from collections.abc import Sequence
from datetime import datetime
from typing import NoReturn

from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import LatestPoint, RecordedReading, SourceKey, SourceReading
from p2pwatch.domain.store_error import StoreError


class FakeSourcePointStore(SourcePointWriter, SourcePointReader):
    """Records each ``record_readings`` call, answering ``kept`` per hash; raises
    ``StoreError`` for ``fail_for``. ``history`` answers ``read_earlier_points`` per source,
    no point by default, and ``baseline`` answers ``has_points_before``, each call noted in
    ``baselines``, the first ``baseline_failures`` raising ``StoreError``."""

    def __init__(
        self,
        *,
        fail_for: set[str] | None = None,
        kept: dict[str, tuple[RecordedReading, ...]] | None = None,
        history: dict[SourceKey, tuple[LatestPoint, ...]] | None = None,
        baseline: bool = True,
        baseline_failures: int = 0,
    ) -> None:
        self.recorded: list[tuple[str, tuple[SourceReading, ...], datetime]] = []
        self.asked: list[tuple[SourceKey, datetime]] = []
        self.baselines: list[datetime] = []
        self.node_ids: set[str] = set()  # every call's
        self._fail_for = fail_for or set()
        self._kept = kept or {}
        self._history = history or {}
        self._baseline = baseline
        self._baseline_failures = baseline_failures

    def record_readings(
        self, file: FileKey, readings: Sequence[SourceReading], read_at: datetime, node_id: str
    ) -> tuple[RecordedReading, ...]:
        self.node_ids.add(node_id)
        if file.native_id in self._fail_for:
            raise StoreError(f"record_readings({file.native_id}) failed")
        self.recorded.append((file.native_id, tuple(readings), read_at))
        return self._kept.get(file.native_id, ())

    def read_latest_point(
        self,
        file: FileKey,
        reading: SourceReading,
        since: datetime,
        before: datetime,
        node_id: str,
    ) -> NoReturn:
        raise AssertionError("the step reads no latest point: the store carries the role")

    def read_earlier_points(
        self, source: SourceKey, before: datetime, node_id: str
    ) -> tuple[LatestPoint, ...]:
        self.node_ids.add(node_id)
        self.asked.append((source, before))
        return self._history.get(source, ())

    def has_points_before(self, before: datetime, node_id: str) -> bool:
        self.node_ids.add(node_id)
        self.baselines.append(before)
        if len(self.baselines) <= self._baseline_failures:
            raise StoreError("has_points_before failed")
        return self._baseline
