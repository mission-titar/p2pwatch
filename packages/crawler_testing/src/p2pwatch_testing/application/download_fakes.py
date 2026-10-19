"""The download use case's doubles, shared by its cycle and loop tests."""

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Literal

from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation
from p2pwatch.domain.source import SourceKey, SourceReading
from p2pwatch.ports.driven.catalog_repository import DownloadCandidate
from p2pwatch.ports.driven.download_client import (
    DownloadRequest,
    DownloadStatus,
    FailureReason,
    WaitingReason,
)
from p2pwatch.ports.driven.repository_errors import RepositoryError
from p2pwatch.ports.driven.source_repository import EarlierPoints, RecordedReading
from p2pwatch_testing.application.fakes import FakeTime


class FakeDownloadClient:
    """Scripted DownloadClient: SCRIPTED ``downloads()`` snapshots, captures the started requests.

    It is the SourceClient too, as the real adapter is: ``readings`` per hash, ``source_reads``
    the hashes read, each read advancing ``fake_time`` by a second when one is given.
    """

    def __init__(
        self,
        *,
        listed: list[tuple[DownloadStatus, ...]] | None = None,
        list_failures: list[Exception] | None = None,
        start_failures: list[Exception] | None = None,
        source_failures: list[Exception] | None = None,
        readings: dict[str, tuple[SourceReading, ...]] | None = None,
        fake_time: FakeTime | None = None,
    ) -> None:
        self._listed = list(listed or [()])
        self._list_failures = list(list_failures or [])
        self._start_failures = list(start_failures or [])
        self._source_failures = list(source_failures or [])
        self._readings = readings or {}
        self._fake_time = fake_time
        self.started: list[DownloadRequest] = []
        self.source_reads: list[str] = []

    async def start(self, request: DownloadRequest) -> None:
        if self._start_failures:
            raise self._start_failures.pop(0)
        self.started.append(request)

    async def downloads(self) -> tuple[DownloadStatus, ...]:
        if self._list_failures:
            raise self._list_failures.pop(0)
        return self._listed.pop(0) if self._listed else ()

    async def sources(self, file: FileKey) -> tuple[SourceReading, ...]:
        self.source_reads.append(file.native_id)
        if self._fake_time is not None:
            self._fake_time.advance(timedelta(seconds=1))
        if self._source_failures:
            raise self._source_failures.pop(0)
        return self._readings.get(file.native_id, ())


class FakeSourceRepo:
    """Records each ``record_readings`` call, answering ``kept`` per hash; raises
    ``RepositoryError`` for ``fail_for``. ``history`` answers ``earlier_points`` per source,
    never useful by default, and ``baseline`` answers ``has_points_before``, each call noted in
    ``baselines``, the first ``baseline_failures`` raising ``RepositoryError``."""

    def __init__(
        self,
        *,
        fail_for: set[str] | None = None,
        kept: dict[str, tuple[RecordedReading, ...]] | None = None,
        history: dict[SourceKey, EarlierPoints] | None = None,
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
            raise RepositoryError(f"record_readings({file.native_id}) failed")
        self.recorded.append((file.native_id, tuple(readings), read_at))
        return self._kept.get(file.native_id, ())

    def earlier_points(self, source: SourceKey, before: datetime, node_id: str) -> EarlierPoints:
        self.node_ids.add(node_id)
        self.asked.append((source, before))
        return self._history.get(
            source, EarlierPoints(has_useful_point=False, latest_known_at=None)
        )

    def has_points_before(self, before: datetime, node_id: str) -> bool:
        self.node_ids.add(node_id)
        self.baselines.append(before)
        if len(self.baselines) <= self._baseline_failures:
            raise RepositoryError("has_points_before failed")
        return self._baseline


class FakeDownloadRepo:
    """In-memory downloads repo (the contract of SqliteDownloadRepository, without SQL).

    Keyed by ``native_id``; ``failures`` and ``waiting`` hold the lifecycle reasons,
    ``queued_at``, ``completed_at`` and ``seen_at`` the instants received, and ``last_seen_at``
    what ``last_seen_at_by_file`` reads back.
    ``fail_set_state_for`` and ``fail_record_completed_for``: hashes for which ``set_state`` or
    ``record_completed`` raises ``RepositoryError``, to simulate a mid-cycle repo failure
    (cf. logic-download#2/error-boundary#2).
    ``fail_active_states``: ``tracked_states()`` raises, to simulate persistence being down
    also at re-read time (every step of the cycle absorbs)."""

    def __init__(
        self,
        *,
        fail_record: bool = False,
        fail_set_state_for: set[str] | None = None,
        fail_record_completed_for: set[str] | None = None,
        fail_active_states: bool = False,
        fail_mark_seen: bool = False,
    ) -> None:
        self.states: dict[str, DownloadState] = {}
        self.failures: dict[str, FailureReason | None] = {}
        self.waiting: dict[str, WaitingReason | None] = {}
        self.sizes: dict[str, int] = {}
        self.queued_at: dict[str, datetime] = {}
        self.completed_at: dict[str, datetime] = {}
        self.seen: list[set[str]] = []
        self.seen_at: list[datetime] = []
        self.last_seen_at: dict[str, datetime] = {}
        self._fail_record = fail_record
        self._fail_set_state_for = fail_set_state_for or set()
        self._fail_record_completed_for = fail_record_completed_for or set()
        self._fail_active_states = fail_active_states
        self._fail_mark_seen = fail_mark_seen
        self._target_ids: dict[str, str] = {}

    def queued_target_id(self, file: FileKey) -> str | None:
        return self._target_ids.get(file.native_id)

    def record_queued(
        self, file: FileKey, target_id: str, size_bytes: int, queued_at: datetime
    ) -> bool:
        if self._fail_record:
            raise RepositoryError("downloads write failed")
        if file.native_id in self.states:
            return False
        self.states[file.native_id] = DownloadState.QUEUED
        self.sizes[file.native_id] = size_bytes
        self.queued_at[file.native_id] = queued_at
        self.last_seen_at[file.native_id] = queued_at
        return True

    def record_completed(self, file: FileKey, completed_at: datetime) -> None:
        if file.native_id in self._fail_record_completed_for:
            raise RepositoryError(f"record_completed({file.native_id}) failed")
        self.states[file.native_id] = DownloadState.COMPLETED
        self.failures[file.native_id] = None
        self.completed_at[file.native_id] = completed_at

    def set_state(
        self,
        file: FileKey,
        state: Literal[DownloadState.DOWNLOADING, DownloadState.FAILED],
        failure_reason: FailureReason | None = None,
    ) -> None:
        if file.native_id in self._fail_set_state_for:
            raise RepositoryError(f"set_state({file.native_id}) failed")
        self.states[file.native_id] = state
        self.failures[file.native_id] = failure_reason

    def is_tracked(self, file: FileKey) -> bool:
        return file.native_id in self.states

    def mark_seen(self, statuses: Iterable[DownloadStatus], seen_at: datetime) -> None:
        if self._fail_mark_seen:
            raise RepositoryError("mark_seen failed")
        statuses = tuple(statuses)
        self.seen.append({status.file.native_id for status in statuses})
        self.seen_at.append(seen_at)
        self.waiting.update({s.file.native_id: s.waiting_reason for s in statuses})
        self.last_seen_at.update({s.file.native_id: seen_at for s in statuses})

    def last_seen_at_by_file(self) -> dict[FileKey, datetime]:
        return {
            FileKey(Network.ED2K, h): last_seen_at
            for h, last_seen_at in self.last_seen_at.items()
            if self.states.get(h) in {DownloadState.QUEUED, DownloadState.DOWNLOADING}
        }

    def tracked_states(self) -> dict[FileKey, DownloadState]:
        if self._fail_active_states:
            raise RepositoryError("tracked_states failed")
        return {FileKey(Network.ED2K, h): state for h, state in self.states.items()}


class FakeCatalogReads:
    """Catalog read side: download_candidates, latest_observation and best_observation scripted."""

    def __init__(
        self,
        *,
        candidates: tuple[DownloadCandidate, ...] = (),
        observations: dict[str, FileObservation] | None = None,
        best: dict[str, FileObservation] | None = None,
    ) -> None:
        self._candidates = candidates
        self._observations = observations or {}
        self._best = best or {}

    def download_candidates(self) -> tuple[DownloadCandidate, ...]:
        return self._candidates

    def latest_observation(self, file: FileKey) -> FileObservation | None:
        return self._observations.get(file.native_id)

    def best_observation(self, file: FileKey) -> FileObservation | None:
        return self._best.get(file.native_id)


class FakeDiskSpace:
    """Scripted free space (the real adapter calls shutil.disk_usage)."""

    def __init__(self, free: int) -> None:
        self.free = free

    def free_bytes(self) -> int:
        return self.free
