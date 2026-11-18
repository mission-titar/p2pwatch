"""The works over the node's aMule client, built anew over each client the node opens, such as
its status reading and its searches, over parts built once, such as the health of each part."""

import sqlite3
from collections.abc import Sequence
from datetime import timedelta

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.adapters.driven.shutil_free_space_meter import ShutilFreeSpaceMeter
from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.application.ports.driven.waker import Waker
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.backoff_registry import BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.download_cycle import DownloadCycle
from p2pwatch.application.steps.download_decider import DownloadDecider
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.application.steps.download_starter import DownloadStarter
from p2pwatch.application.steps.download_tracker import DownloadTracker
from p2pwatch.application.steps.keyword_search import keyword_searches
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.application.steps.source_watcher import SourceWatcher
from p2pwatch.application.steps.status_watcher import StatusWatcher
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.composition.work_time_limits import AmuleWorkTimeLimits
from p2pwatch.domain.crawler_config import DownloadConfig
from p2pwatch.domain.download.disk_space import download_tracking_dependency
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.matching.models import TargetSegment
from p2pwatch.domain.search.keywords import dedupe_keywords
from p2pwatch.domain.status_reading import channel_dependency, client_dependency
from p2pwatch.domain.work_dependencies import (
    keyword_search_dependency,
    source_tracking_dependency,
    status_reading_dependency,
)


def works_in_start_order[W](
    *, status_watcher: W, tracking: Sequence[W], searches: Sequence[W]
) -> list[W]:
    """The works in the order the supervisor starts them: the status reading, then download and
    source tracking where configured, then the searches, which send their requests last."""
    return [status_watcher, *tracking, *searches]


class DownloadSteps:
    """The download steps that hold no client, such as the tracker and when it would call each
    download lost: built once, a client built anew finds them as the old one left them."""

    def __init__(
        self,
        download_config: DownloadConfig,
        *,
        client_name: ClientName,
        targets: Sequence[TargetSegment],
        local_connection: sqlite3.Connection,
        catalog_connection: sqlite3.Connection,
        observation_store: SqliteObservationStore,
        decision_store: SqliteDecisionStore,
        waker: Waker,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        observability_dispatcher: ObservabilityDispatcher,
        node_health: NodeHealth,
        node_id: NodeId,
    ) -> None:
        self._config = download_config
        self._client_name = client_name
        self._observation_store = observation_store
        self._waker = waker
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._observability_dispatcher = observability_dispatcher
        self._node_id = node_id
        # One part for the disk's readings, the client's networks and the cycle's bugs.
        self.download_tracking = download_tracking_dependency(client_name)
        self._source_tracking = source_tracking_dependency(client_name)
        # Both share ``local_connection`` and the catalog's stores: one writer, on the event loop.
        self._tracked_download_store = SqliteTrackedDownloadStore(local_connection)
        self._source_point_store = SqliteSourcePointStore(catalog_connection)
        self._labeler = DownloadLabeler(
            observation_reader=observation_store,
            decision_reader=decision_store,
            tracked_download_reader=self._tracked_download_store,
            targets=targets,
        )
        self._tracker = DownloadTracker(
            tracked_download_writer=self._tracked_download_store,
            tracked_download_reader=self._tracked_download_store,
            download_labeler=self._labeler,
            lost_after=download_config.lost_after,
            wall_clock=wall_clock,
            monotonic_clock=monotonic_clock,
            observability_dispatcher=observability_dispatcher,
            node_id=node_id,
            logger=StdlibLogger(DownloadTracker.__module__),
        )
        self._decider = DownloadDecider(
            free_space_meter=ShutilFreeSpaceMeter(download_config.output_directory),
            min_free_bytes=download_config.min_free_bytes,
            decision_reader=decision_store,
            observation_reader=observation_store,
            tracked_download_writer=self._tracked_download_store,
            tracked_download_reader=self._tracked_download_store,
            targets=targets,
            download_tracker=self._tracker,
            wall_clock=wall_clock,
            observability_dispatcher=observability_dispatcher,
            node_health=node_health,
            download_tracking_dependency=self.download_tracking,
            logger=StdlibLogger(DownloadDecider.__module__),
        )

    def works_over(
        self, client: AmuleApiClient, *, time_limit: timedelta
    ) -> tuple[SupervisedWork, SupervisedWork]:
        """Download tracking and source tracking over ``client``, each turn cut at
        ``time_limit``."""
        download_cycle = DownloadCycle(
            client_name=self._client_name,
            download_client=client,
            download_tracker=self._tracker,
            download_decider=self._decider,
            download_starter=DownloadStarter(
                download_client=client,
                tracked_download_writer=self._tracked_download_store,
                tracked_download_reader=self._tracked_download_store,
                observation_reader=self._observation_store,
                logger=StdlibLogger(DownloadStarter.__module__),
            ),
            poll_interval_seconds=self._config.poll_interval_seconds,
            monotonic_clock=self._monotonic_clock,
            waker=self._waker,
            logger=StdlibLogger(DownloadCycle.__module__),
        )
        source_watcher = SourceWatcher(
            client_name=self._client_name,
            download_client=client,
            source_client=client,
            tracked_download_reader=self._tracked_download_store,
            source_point_writer=self._source_point_store,
            source_point_reader=self._source_point_store,
            download_labeler=self._labeler,
            reappeared_after=self._config.reappeared_after,
            sources_interval=self._config.sources_interval,
            time_between_source_reads=self._config.time_between_source_reads,
            wall_clock=self._wall_clock,
            monotonic_clock=self._monotonic_clock,
            observability_dispatcher=self._observability_dispatcher,
            node_id=self._node_id,
            logger=StdlibLogger(SourceWatcher.__module__),
        )
        return (
            SupervisedWork(
                work=download_cycle, time_limit=time_limit, dependencies=(self.download_tracking,)
            ),
            SupervisedWork(
                work=source_watcher, time_limit=time_limit, dependencies=(self._source_tracking,)
            ),
        )


class AmuleClientWorks:
    """Builds every work over one aMule client, such as its status reading and its searches, on
    parts built once: a client built anew finds each part's health as the old one left it."""

    def __init__(
        self,
        *,
        client_name: ClientName,
        channels: Sequence[Channel],
        keywords: Sequence[str],
        download_steps: DownloadSteps | None,
        backoff: BackoffRegistry,
        backoff_saver: BackoffSaver,
        cataloguer: Cataloguer,
        status_reading_writer: StatusReadingWriter,
        node_health: NodeHealth,
        observability_dispatcher: ObservabilityDispatcher,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        time_limits: AmuleWorkTimeLimits,
    ) -> None:
        self._client_name = client_name
        self._keywords = keywords
        self._download_steps = download_steps  # None: the node downloads nothing
        self._backoff = backoff
        self._backoff_saver = backoff_saver
        self._cataloguer = cataloguer
        self._status_reading_writer = status_reading_writer
        self._node_health = node_health
        self._observability_dispatcher = observability_dispatcher
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._time_limits = time_limits
        self._client_dependency = client_dependency(client_name)
        self._status_reading_dependency = status_reading_dependency(client_name)
        # Each channel's readings and the bugs of its searches are recorded on one part.
        self._channel_dependencies = {
            channel: channel_dependency(client_name=client_name, channel=channel)
            for channel in channels
        }
        self._search_dependencies = {
            (keyword, channel): keyword_search_dependency(
                keyword=keyword, client_name=client_name, channel=channel
            )
            for keyword in dedupe_keywords(keywords)
            for channel in channels
        }

    def over(self, client: AmuleApiClient) -> list[SupervisedWork]:
        """Every work over ``client``, in the order the supervisor starts them."""
        download_steps = self._download_steps
        status_watcher = StatusWatcher(
            client_name=self._client_name,
            client=client,
            wall_clock=self._wall_clock,
            monotonic_clock=self._monotonic_clock,
            observability_dispatcher=self._observability_dispatcher,
            status_reading_writer=self._status_reading_writer,
            node_health=self._node_health,
            client_dependency=self._client_dependency,
            channel_dependencies=self._channel_dependencies,
            download_tracking_dependency=(
                None if download_steps is None else download_steps.download_tracking
            ),
        )
        search_worker = SearchWorker(
            client_name=self._client_name,
            client=client,
            backoff=self._backoff,
            cataloguer=self._cataloguer,
            observability_dispatcher=self._observability_dispatcher,
            logger=StdlibLogger(SearchWorker.__module__),
        )
        return works_in_start_order(
            status_watcher=SupervisedWork(
                work=status_watcher,
                time_limit=self._time_limits.of_status_reading(),
                dependencies=(self._status_reading_dependency,),
            ),
            tracking=(
                ()
                if download_steps is None
                else download_steps.works_over(client, time_limit=self._time_limits.of_tracking())
            ),
            searches=keyword_searches(
                search_workers=[search_worker],
                keywords=self._keywords,
                backoff_saver=self._backoff_saver,
                monotonic_clock=self._monotonic_clock,
                time_limit_of=self._time_limits.of_search,
                search_dependency_of=lambda keyword, *, channel: self._search_dependencies[
                    keyword, channel
                ],
                node_health=self._node_health,
                channel_dependencies=self._channel_dependencies.values(),
            ),
        )
