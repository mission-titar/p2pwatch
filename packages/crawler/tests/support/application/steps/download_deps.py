"""What the download stages' tests share: their fixtures' values and the deps they build."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from catalog_matching.domain.models import TargetSegment
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.download.states import FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore

NODE = "n1"
HASH_A = "a" * 32
HASH_B = "b" * 32
HASH_C = "c" * 32
SEEN_AT = datetime(2026, 6, 12, tzinfo=UTC)

TARGETS = (
    TargetSegment(
        season=2, seasonal_number=11, absolute_number=62, letter="A", title="t", status="lost"
    ),
    TargetSegment(
        season=2,
        seasonal_number=63,
        absolute_number=63,
        letter="A",
        title="t2",
        status="complete",
    ),
)


def key(hash_hex: str) -> FileKey:
    return FileKey(Network.ED2K, hash_hex)


def observation(hash_hex: str, filename: str, size_bytes: int) -> FileObservation:
    reported_file = ReportedFile(key(hash_hex), filename, size_bytes, 1, "keroro")
    return FileObservation(reported_file, SEEN_AT)


def candidate(hash_hex: str, target_id: str) -> DownloadCandidate:
    return DownloadCandidate(file=key(hash_hex), target_id=target_id)


def status(
    hash_hex: str,
    *,
    done: int = 0,
    total: int = 0,
    completed: bool = False,
    waiting: WaitingReason | None = None,
    failure: FailureReason | None = None,
) -> DownloadStatus:
    return DownloadStatus(key(hash_hex), done, total, completed, waiting, failure)


def started(client: FakeDownloadClient) -> list[str]:
    return [request.file.native_id for request in client.started]


def build_deps(
    *,
    client: FakeDownloadClient,
    source_client: FakeSourceClient | None = None,
    tracked_download_store: FakeTrackedDownloadStore | SqliteTrackedDownloadStore,
    decision_reader: FakeDecisionReader | None = None,
    observation_reader: FakeObservationReader | None = None,
    free: int = 1_000_000,
    min_free: int = 0,
    lost_after: timedelta = timedelta(days=1),
    event_emitter: FakeEventEmitter | None = None,
    targets: Sequence[TargetSegment] | None = None,
    sources: FakeSourcePointStore | SqliteSourcePointStore | None = None,
    fake_time: FakeTime | None = None,
    sources_interval: timedelta = timedelta(seconds=30),
    logger: FakeLogger | None = None,
) -> DownloadDeps:
    fake_time = fake_time or FakeTime()
    sources = sources or FakeSourcePointStore()
    return DownloadDeps(
        download_client=client,
        source_client=source_client or FakeSourceClient(),
        tracked_download_writer=tracked_download_store,
        tracked_download_reader=tracked_download_store,
        source_point_writer=sources,
        source_point_reader=sources,
        decision_reader=decision_reader or FakeDecisionReader(),
        observation_reader=observation_reader or FakeObservationReader(),
        targets=targets if targets is not None else TARGETS,
        free_space_meter=FakeFreeSpaceMeter(free),
        min_free_bytes=min_free,
        lost_after=lost_after,
        poll_interval_seconds=30.0,
        reappeared_after=timedelta(hours=12),
        sources_interval=sources_interval,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        event_emitter=event_emitter or FakeEventEmitter(),
        logger=logger or FakeLogger(),
    )
