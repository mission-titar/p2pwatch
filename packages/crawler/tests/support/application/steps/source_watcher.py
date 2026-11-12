"""The source watcher the source tracking tests build, over the download stages' fixtures."""

from collections.abc import Sequence
from datetime import timedelta

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.source_watcher import SourceWatcher
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.matching.models import TargetSegment
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_cycle import NODE_ID, TARGETS
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes


def build_watcher(
    *,
    client: FakeDownloadClient,
    source_client: FakeSourceClient | None = None,
    tracked_download_store: FakeTrackedDownloadStore,
    decision_reader: FakeDecisionReader | None = None,
    observation_reader: FakeObservationReader | None = None,
    observability_dispatcher: ObservabilityDispatcher | None = None,
    targets: Sequence[TargetSegment] | None = None,
    sources: FakeSourcePointStore | SqliteSourcePointStore | None = None,
    fake_time: FakeTime | None = None,
    sources_interval: timedelta = timedelta(seconds=30),
    time_between_source_reads: timedelta = timedelta(seconds=60),
    logger: FakeLogger | None = None,
) -> SourceWatcher:
    fake_time = fake_time or FakeTime()
    sources = sources or FakeSourcePointStore()
    return SourceWatcher(
        client_name=ClientName("amuled"),
        download_client=client,
        source_client=source_client or FakeSourceClient(),
        tracked_download_reader=tracked_download_store,
        source_point_writer=sources,
        source_point_reader=sources,
        download_labeler=DownloadLabeler(
            observation_reader=observation_reader or FakeObservationReader(),
            decision_reader=decision_reader or FakeDecisionReader(),
            tracked_download_reader=tracked_download_store,
            targets=targets if targets is not None else TARGETS,
        ),
        reappeared_after=timedelta(hours=12),
        sources_interval=sources_interval,
        time_between_source_reads=time_between_source_reads,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        observability_dispatcher=(observability_dispatcher or ObservabilityOverFakes().dispatcher),
        node_id=NODE_ID,
        logger=logger or FakeLogger(),
    )
