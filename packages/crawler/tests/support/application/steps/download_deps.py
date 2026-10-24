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
from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.download_decider import DownloadDecider
from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.application.steps.download_starter import DownloadStarter
from p2pwatch.application.steps.download_tracker import DownloadTracker
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.download.states import FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

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
    return FileObservation(reported_file, SEEN_AT, NODE)


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
    free_space_meter: FreeSpaceMeter | None = None,
    min_free: int = 0,
    lost_after: timedelta = timedelta(days=1),
    observability_dispatcher: ObservabilityDispatcher | None = None,
    targets: Sequence[TargetSegment] | None = None,
    sources: FakeSourcePointStore | SqliteSourcePointStore | None = None,
    fake_time: FakeTime | None = None,
    sources_interval: timedelta = timedelta(seconds=30),
    time_between_source_reads: timedelta = timedelta(seconds=60),
    logger: FakeLogger | None = None,
    wall_clock: WallClock | None = None,
) -> DownloadDeps:
    fake_time = fake_time or FakeTime()
    wall_clock = wall_clock or fake_time.wall
    sources = sources or FakeSourcePointStore()
    decision_reader = decision_reader or FakeDecisionReader()
    observation_reader = observation_reader or FakeObservationReader()
    targets = targets if targets is not None else TARGETS
    observability_dispatcher = observability_dispatcher or ObservabilityOverFakes().dispatcher
    logger = logger or FakeLogger()
    download_labeler = DownloadLabeler(
        observation_reader=observation_reader,
        decision_reader=decision_reader,
        tracked_download_reader=tracked_download_store,
        targets=targets,
    )
    download_tracker = DownloadTracker(
        tracked_download_writer=tracked_download_store,
        tracked_download_reader=tracked_download_store,
        download_labeler=download_labeler,
        lost_after=lost_after,
        wall_clock=wall_clock,
        monotonic_clock=fake_time.monotonic,
        observability_dispatcher=observability_dispatcher,
        logger=logger,
    )
    return DownloadDeps(
        download_client=client,
        source_client=source_client or FakeSourceClient(),
        tracked_download_reader=tracked_download_store,
        source_point_writer=sources,
        source_point_reader=sources,
        download_labeler=download_labeler,
        poll_interval_seconds=30.0,
        reappeared_after=timedelta(hours=12),
        sources_interval=sources_interval,
        time_between_source_reads=time_between_source_reads,
        wall_clock=wall_clock,
        monotonic_clock=fake_time.monotonic,
        observability_dispatcher=observability_dispatcher,
        logger=logger,
        download_tracker=download_tracker,
        download_decider=DownloadDecider(
            free_space_meter=free_space_meter or FakeFreeSpaceMeter(free),
            min_free_bytes=min_free,
            decision_reader=decision_reader,
            observation_reader=observation_reader,
            tracked_download_writer=tracked_download_store,
            tracked_download_reader=tracked_download_store,
            targets=targets,
            download_tracker=download_tracker,
            wall_clock=wall_clock,
            observability_dispatcher=observability_dispatcher,
            logger=logger,
        ),
        download_starter=DownloadStarter(
            download_client=client,
            tracked_download_writer=tracked_download_store,
            tracked_download_reader=tracked_download_store,
            observation_reader=observation_reader,
            logger=logger,
        ),
    )
