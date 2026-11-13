"""What the download stages' tests share: their fixtures' values and the cycle they build."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.download_cycle import DownloadCycle
from p2pwatch.application.steps.download_decider import DownloadDecider
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.application.steps.download_starter import DownloadStarter
from p2pwatch.application.steps.download_tracker import DownloadTracker
from p2pwatch.application.steps.health_event_translator import HealthEventTranslator
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.download.states import FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.identifiers import ClientName, Keyword, NodeId
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.matching.models import TargetSegment
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.work_components import download_tracking_component
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

NODE_ID = NodeId("n1")
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
        status="found",
    ),
)


def key(hash_hex: str) -> FileKey:
    return FileKey(network=Network.ED2K, native_id=hash_hex)


def observation(hash_hex: str, *, filename: str, size_bytes: int) -> FileObservation:
    reported_file = ReportedFile(
        file=key(hash_hex),
        filename=filename,
        size_bytes=size_bytes,
        source_count=1,
        keyword=Keyword("keroro"),
    )
    return FileObservation(reported_file=reported_file, observed_at=SEEN_AT, node_id=NODE_ID)


def candidate(hash_hex: str, *, target_id: TargetId) -> DownloadCandidate:
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
    return DownloadStatus(
        file=key(hash_hex),
        bytes_done=done,
        size_bytes=total,
        completed=completed,
        waiting_reason=waiting,
        failure_reason=failure,
    )


def started(client: FakeDownloadClient) -> list[str]:
    return [request.file.native_id for request in client.started]


def build_cycle(
    *,
    client: FakeDownloadClient,
    tracked_download_store: FakeTrackedDownloadStore | SqliteTrackedDownloadStore,
    decision_reader: FakeDecisionReader | None = None,
    observation_reader: FakeObservationReader | None = None,
    free: int = 1_000_000,
    free_space_meter: FreeSpaceMeter | None = None,
    min_free: int = 0,
    lost_after: timedelta = timedelta(days=1),
    observability_dispatcher: ObservabilityDispatcher | None = None,
    targets: Sequence[TargetSegment] | None = None,
    fake_time: FakeTime | None = None,
    logger: FakeLogger | None = None,
    wall_clock: WallClock | None = None,
    poll_interval_seconds: float = 30.0,
    waker: FakeWaker | None = None,
    wait_clock: MonotonicClock | None = None,
    tracking_component: Component | None = None,
) -> DownloadCycle:
    fake_time = fake_time or FakeTime()
    wall_clock = wall_clock or fake_time.wall
    decision_reader = decision_reader or FakeDecisionReader()
    observation_reader = observation_reader or FakeObservationReader()
    targets = targets if targets is not None else TARGETS
    observability_dispatcher = observability_dispatcher or ObservabilityOverFakes().dispatcher
    logger = logger or FakeLogger()
    # As the composition: the free-space reading's transitions become today's disk alert.
    health_recorder = HealthRecorder(
        logger=FakeLogger(),
        subscribers=(
            HealthEventTranslator(
                observability_dispatcher=observability_dispatcher, node_id=NODE_ID
            ).translate,
        ),
    )
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
        node_id=NODE_ID,
        logger=logger,
    )
    return DownloadCycle(
        client_name=ClientName("amuled"),
        download_client=client,
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
            record_outcome=health_recorder.record,
            download_tracking_component=(
                tracking_component or download_tracking_component(ClientName("amuled"))
            ),
            logger=logger,
        ),
        download_starter=DownloadStarter(
            download_client=client,
            tracked_download_writer=tracked_download_store,
            tracked_download_reader=tracked_download_store,
            observation_reader=observation_reader,
            logger=logger,
        ),
        poll_interval_seconds=poll_interval_seconds,
        monotonic_clock=wait_clock or fake_time.monotonic,
        waker=waker or FakeWaker(),
        logger=logger,
    )
