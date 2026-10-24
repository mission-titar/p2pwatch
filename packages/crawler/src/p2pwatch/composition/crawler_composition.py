"""Composition root: loads the config, assembles the crawler it describes, then runs it.

COMPOSITION ring (the only one allowed to import adapters AND application). Builds:
- ONE ``SqliteObservationStore`` + ``SqliteCatalogScanReader``, ``SqliteDecisionStore``,
  ``SqliteNodeIdStore``, ``SqlitePolicyFingerprintStore`` and ``SqliteBackoffStateStore``
  (single writer, invariant §11), connections opened via ``open_catalog``/``open_local``
  (migrations checked at startup, fail-fast §14).
- the ``MatchingEngine`` (once),
- ONE ``AmuleApiClient`` + ``SearchWorker`` on the one amuled the core drives, whose
  session the status and download loops share.

Loops: the search tasks (``SearchTaskRunner``), the status loop, and the download loop when
configured, which ``CrawlerLifecycle`` runs until ``PosixProcess`` or the webui requests the
shutdown.
OBSERVABLE & BOUNDED shutdown (spec §6): long-lived resources are closed AFTER the full unwind of
the loops (no worker can write anymore), all within ``shutdown_deadline_seconds``.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator, Callable, Coroutine, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path, PurePath

import apprise
import httpx
from prometheus_client import CollectorRegistry, start_http_server

import p2pwatch.adapters.driving.webui
from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.asyncio_monotonic_clock import AsyncioMonotonicClock
from p2pwatch.adapters.driven.asyncio_run_state_store import AsyncioRunStateStore
from p2pwatch.adapters.driven.asyncio_waker import AsyncioWaker
from p2pwatch.adapters.driven.config.crawler_config import load_config
from p2pwatch.adapters.driven.in_memory_status_reading_store import InMemoryStatusReadingStore
from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.adapters.driven.observability.prometheus_metrics_recorder import (
    PrometheusMetricsRecorder,
    start_metrics_server,
)
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog, open_local
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_backoff_state_store import (
    SqliteBackoffStateStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_file_reader import (
    SqliteCatalogFileReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_coverage_reader import SqliteCoverageReader
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_id_store import SqliteNodeIdStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_node_state_reader import (
    SqliteNodeStateReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_policy_fingerprint_store import (
    SqlitePolicyFingerprintStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_point_store import (
    SqliteSourcePointStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_reader import SqliteSourceReader
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_sql_executor import SqliteSqlExecutor
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.adapters.driven.random_jitter_generator import RandomJitterGenerator
from p2pwatch.adapters.driven.shutil_free_space_meter import ShutilFreeSpaceMeter
from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from p2pwatch.adapters.driven.uuid4_node_id_generator import Uuid4NodeIdGenerator
from p2pwatch.adapters.driving.process.posix_process import PosixProcess
from p2pwatch.adapters.driving.webui.app import build_app as build_webui_app
from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.crawler_lifecycle import CrawlerLifecycle
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.ports.driving.crawler_runner import CrawlerRunner
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.download_cycle import DownloadCycle
from p2pwatch.application.steps.download_decider import DownloadDecider
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.application.steps.download_loop import DownloadLoop
from p2pwatch.application.steps.download_starter import DownloadStarter
from p2pwatch.application.steps.download_tracker import DownloadTracker
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.loop_supervisor import LoopSupervisor
from p2pwatch.application.steps.node_id_resolver import NodeIdResolver
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.search_tasks import SearchTaskRunner
from p2pwatch.application.steps.search_worker import (
    BackoffPolicy,
    BackoffRegistry,
    SearchWorker,
)
from p2pwatch.application.steps.source_watcher import SourceWatcher
from p2pwatch.application.steps.status_loop import StatusLoop
from p2pwatch.application.use_cases.describe_file import DescribeFile
from p2pwatch.application.use_cases.describe_node import DescribeNode
from p2pwatch.application.use_cases.describe_source import DescribeSource
from p2pwatch.application.use_cases.describe_source_name import DescribeSourceName
from p2pwatch.application.use_cases.list_files import ListFiles
from p2pwatch.application.use_cases.list_sources import ListSources
from p2pwatch.application.use_cases.pause_crawl import PauseCrawl
from p2pwatch.application.use_cases.request_shutdown import RequestShutdown
from p2pwatch.application.use_cases.resume_crawl import ResumeCrawl
from p2pwatch.application.use_cases.run_console_query import RunConsoleQuery
from p2pwatch.application.use_cases.summarize_crawl import SummarizeCrawl
from p2pwatch.domain.config_defaults import AMULE_CLIENT_NAME
from p2pwatch.domain.console_query import ConsoleDatabase
from p2pwatch.domain.crawler_config import CrawlerConfig, LoadedConfig
from p2pwatch.domain.matching_read import MatchingExplainer

_logger = logging.getLogger(__name__)

_AMULE_API_TIMEOUT_SECONDS = 10.0
# Rows asked for per list request. Every list route caps at 100 when `limit` is omitted, which
# would silently truncate the shared-file sweep completion detection depends on (§7.5).
_AMULE_API_PAGE_SIZE = 500
# How often a search's progress is read: local traffic with our own daemon.
_AMULE_API_PROGRESS_POLL_INTERVAL = timedelta(seconds=5)
_WEBUI_START_TIMEOUT_SECONDS = 5.0
# uvicorn polls ``should_exit`` every 0.1 s, so the join normally returns well within its bound.
_WEBUI_JOIN_TIMEOUT_SECONDS = 5.0
# The metrics server stops on the event loop, where no shutdown deadline can cut a blocking call.
_METRICS_SERVER_JOIN_TIMEOUT_SECONDS = 1.0
# How many SQLite VM steps the SQL console runs between two checks of its query budget.
_CONSOLE_BUDGET_CHECK_INSTRUCTIONS = 1000
# A longer filename is never matched: it bounds the matching's cost on what a peer advertises.
_MAX_FILENAME_LENGTH = 4096
# One INFO progress line per this many files, so a long sweep visibly advances.
_REEVALUATION_PROGRESS_EVERY_FILES = 200


def _print_progress(message: str) -> None:
    """Human shutdown line on stderr (spec §6: observable progress, outside logging)."""
    print(message, file=sys.stderr, flush=True)


@asynccontextmanager
async def resource_stack() -> AsyncIterator[AsyncExitStack]:
    """The stack of the resources the crawler holds, closed on exit."""
    resources = AsyncExitStack()
    try:
        yield resources
    finally:
        # Best effort after a fired deadline or a failed setup: its failures never mask the first.
        with suppress(BaseException):
            await resources.aclose()


def _backoff_policy(config: CrawlerConfig) -> BackoffPolicy:
    """Unpacks the backoff config into primitives for the application (dependency rule)."""
    backoff = config.search.backoff
    return BackoffPolicy(
        base_seconds=backoff.base_seconds,
        cap_seconds=backoff.cap_seconds,
        factor=backoff.factor,
        jitter_ratio=backoff.jitter_ratio,
    )


class CrawlerComposition(CrawlerRunner):
    """Loads the config, then assembles and runs the crawler it describes (composition root)."""

    def __init__(
        self,
        *,
        webui_address: tuple[str, int],
        amule_api_address: tuple[str, int],
        env: Mapping[str, str],
        root_logger: logging.Logger,
    ) -> None:
        self._webui_address = webui_address
        self._amule_api_address = amule_api_address
        self._env = env
        self._root_logger = root_logger

    def _amule_api_client(
        self, crawler_config: CrawlerConfig, monotonic_clock: MonotonicClock
    ) -> AmuleApiClient:
        """The node's one session on amuled, paced on the composition's monotonic clock."""
        host, port = self._amule_api_address
        return AmuleApiClient(
            host,
            port,
            crawler_config.amule_api_password,
            timeout_seconds=_AMULE_API_TIMEOUT_SECONDS,
            page_size=_AMULE_API_PAGE_SIZE,
            progress_poll_interval=_AMULE_API_PROGRESS_POLL_INTERVAL,
            monotonic_clock=monotonic_clock,
            transport_factory=httpx.AsyncHTTPTransport,
        )

    async def _start_webui(
        self,
        *,
        config: LoadedConfig,
        stack: AsyncExitStack,
        status_reading_store: InMemoryStatusReadingStore,
        run_state_store: AsyncioRunStateStore,
        shutdown_requester: RequestShutdown,
        engine: MatchingEngine,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
    ) -> None:
        """Start the read-only webui on its OWN thread + loop (spec §5). It shares with the crawler
        the parsed config (immutable), the engine and the clocks (no state after their
        construction), the status reading store (whole snapshots swapped, never mutated) and the
        run state (every change scheduled on the crawler's loop).
        It reads through its OWN ``ThreadReadConnections``, one connection per thread. Its stop is
        registered on ``stack`` so it runs during the normal LIFO unwind, AFTER the loops stop."""
        crawler_config = config.crawler_config
        webui_package_directory = Path(p2pwatch.adapters.driving.webui.__file__).parent
        local_read_connections = ThreadReadConnections(crawler_config.local_db_path)
        node_state_reader = SqliteNodeStateReader(local_read_connections)
        catalog_read_connections = ThreadReadConnections(crawler_config.catalog_db_path)
        catalog_file_reader = SqliteCatalogFileReader(catalog_read_connections)
        source_reader = SqliteSourceReader(catalog_read_connections)
        app = build_webui_app(
            target_segments=config.targets,
            templates_directory=webui_package_directory / "templates",
            static_directory=webui_package_directory / "static",
            crawl_pauser=PauseCrawl(run_state_store),
            crawl_resumer=ResumeCrawl(run_state_store),
            shutdown_requester=shutdown_requester,
            crawl_summarizer=SummarizeCrawl(
                target_ids=tuple(target.target_id for target in config.targets),
                coverage_reader=SqliteCoverageReader(catalog_read_connections),
                node_state_reader=node_state_reader,
                run_state_reader=run_state_store,
                status_reading_reader=status_reading_store,
                monotonic_clock=monotonic_clock,
            ),
            node_describer=DescribeNode(node_state_reader),
            file_lister=ListFiles(catalog_file_reader),
            file_describer=DescribeFile(
                catalog_file_reader=catalog_file_reader,
                source_reader=source_reader,
                explainer=MatchingExplainer(engine=engine),
                wall_clock=wall_clock,
                source_period_gap=crawler_config.webui.source_period_gap,
            ),
            source_lister=ListSources(source_reader),
            source_describer=DescribeSource(
                source_reader=source_reader,
                wall_clock=wall_clock,
                source_period_gap=crawler_config.webui.source_period_gap,
            ),
            source_name_describer=DescribeSourceName(
                source_reader=source_reader,
                wall_clock=wall_clock,
                source_period_gap=crawler_config.webui.source_period_gap,
            ),
            console_query_runner=RunConsoleQuery(
                {
                    ConsoleDatabase.CATALOG: SqliteSqlExecutor(
                        Path(crawler_config.catalog_db_path),
                        monotonic_clock,
                        budget_check_instructions=_CONSOLE_BUDGET_CHECK_INSTRUCTIONS,
                    ),
                    ConsoleDatabase.LOCAL: SqliteSqlExecutor(
                        Path(crawler_config.local_db_path),
                        monotonic_clock,
                        budget_check_instructions=_CONSOLE_BUDGET_CHECK_INSTRUCTIONS,
                    ),
                }
            ),
            amule_url=crawler_config.webui.amule_url,
        )
        server_thread = UvicornServerThread(
            app,
            self._webui_address,
            start_timeout_seconds=_WEBUI_START_TIMEOUT_SECONDS,
            join_timeout_seconds=_WEBUI_JOIN_TIMEOUT_SECONDS,
            serving_resources=(catalog_read_connections, local_read_connections),
        )
        stack.push_async_callback(server_thread.stop)
        await server_thread.start()

    async def run_crawler(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        """Opens the resources under ``PosixProcess``, runs ``CrawlerLifecycle`` to shutdown (§6).

        Only the shutdown is bounded: an overrun raises ``TimeoutError``, and the resource stack
        then closes what is left, before ``PosixProcess`` gives the signals back.
        """
        config = load_config(Path(config_path), Path(targets_path), Path(matcher_path), self._env)
        crawler_config = config.crawler_config
        self._root_logger.setLevel(crawler_config.observability.log_level)
        # Startup version line (spec 2026-07-10-git-driven-versioning): the number baked into the
        # installed wheel by the build (setuptools-scm / SETUPTOOLS_SCM_PRETEND_VERSION), so an
        # operator can correlate a running node to a release.
        _logger.info("p2pwatch version %s", version("p2pwatch"))
        wall_clock = SystemWallClock()
        monotonic_clock = AsyncioMonotonicClock()
        waker = AsyncioWaker()
        loop = asyncio.get_running_loop()
        # On the crawler's OWN loop, so the webui thread changes it thread-safely.
        run_state_store = AsyncioRunStateStore(loop=loop)
        shutdown_requester = RequestShutdown(run_state_store)
        async with PosixProcess(shutdown_requester), resource_stack() as stack:
            catalog_connection = open_catalog(crawler_config.catalog_db_path)
            stack.callback(catalog_connection.close)
            local_connection = open_local(crawler_config.local_db_path)
            stack.callback(local_connection.close)

            node_id_store = SqliteNodeIdStore(local_connection)
            policy_fingerprint_store = SqlitePolicyFingerprintStore(local_connection)
            observability = crawler_config.observability
            registry = CollectorRegistry()
            notifier = AppriseNotifier(
                tuple((t.url, t.audience, t.node_prefix) for t in observability.notifications),
                apprise_factory=apprise.Apprise,
            )
            observability_dispatcher = ObservabilityDispatcher(
                logger=StdlibLogger(ObservabilityDispatcher.__module__),
                metrics_recorder=PrometheusMetricsRecorder(registry),
                notifier=notifier,
                notification_timeout_seconds=observability.notification_timeout_seconds,
            )
            stack.callback(
                start_metrics_server(
                    registry,
                    observability.metrics_port,
                    start_http_server,
                    join_timeout_seconds=_METRICS_SERVER_JOIN_TIMEOUT_SECONDS,
                )
            )
            observation_store = SqliteObservationStore(catalog_connection)
            catalog_scan_reader = SqliteCatalogScanReader(catalog_connection)
            decision_store = SqliteDecisionStore(catalog_connection)
            backoff_state_store = SqliteBackoffStateStore(local_connection)
            engine = MatchingEngine(
                config.matcher_config, config.targets, max_filename_length=_MAX_FILENAME_LENGTH
            )
            status_reading_store = InMemoryStatusReadingStore((AMULE_CLIENT_NAME,))
            # In-process webui (spec §5): own thread + loop, started EARLY (before the daemon client
            # + startup re-evaluation) so it is up promptly and stays isolated from the crawler's
            # synchronous work. Gated by ``webui.enabled``; a crash degrades (spec §17.1). Its
            # graceful stop is on ``stack`` → runs at the normal shutdown unwind (after the database
            # connections are pushed, so it stops the thread before those close in LIFO teardown).
            if crawler_config.webui.enabled:
                await self._start_webui(
                    config=config,
                    stack=stack,
                    status_reading_store=status_reading_store,
                    run_state_store=run_state_store,
                    shutdown_requester=shutdown_requester,
                    engine=engine,
                    wall_clock=wall_clock,
                    monotonic_clock=monotonic_clock,
                )
            # SHARED backoff registry: built ONCE, resumes its waits at the lifecycle's start
            # (backoff survives restart, spec §3/§7), injected into ALL workers + passed to the
            # search tasks that persist it. Single writer on the event loop.
            backoff = BackoffRegistry(
                _backoff_policy(crawler_config),
                wall_clock,
                monotonic_clock,
                RandomJitterGenerator(jitter_seed=None),  # seeded by the system's entropy
                backoff_state_store,
            )
            file_judge = FileJudge(
                observation_reader=observation_store,
                decision_writer=decision_store,
                decision_reader=decision_store,
                engine=engine,
                waker=waker,
                observability_dispatcher=observability_dispatcher,
                wall_clock=wall_clock,
            )
            cataloguer = Cataloguer(
                observation_writer=observation_store,
                file_judge=file_judge,
                observability_dispatcher=observability_dispatcher,
                wall_clock=wall_clock,
                logger=StdlibLogger(Cataloguer.__module__),
            )
            client = self._amule_api_client(crawler_config, monotonic_clock)
            stack.push_async_callback(client.close)
            await client.open()
            workers = [
                SearchWorker(
                    client_name=AMULE_CLIENT_NAME,
                    client=client,
                    backoff=backoff,
                    cataloguer=cataloguer,
                    observability_dispatcher=observability_dispatcher,
                    logger=StdlibLogger(SearchWorker.__module__),
                )
            ]
            # The status and download loops share the search session: one session per node.
            status_loop = StatusLoop(
                client_name=AMULE_CLIENT_NAME,
                client=client,
                wall_clock=wall_clock,
                monotonic_clock=monotonic_clock,
                observability_dispatcher=observability_dispatcher,
                run_state_reader=run_state_store,
                status_reading_writer=status_reading_store,
            )
            search_tasks = SearchTaskRunner(
                workers=workers,
                keywords=crawler_config.search.keywords,
                run_state_reader=run_state_store,
                backoff=backoff,
                backoff_state_writer=backoff_state_store,
                monotonic_clock=monotonic_clock,
                logger=StdlibLogger(SearchTaskRunner.__module__),
            )
            loops: list[Callable[[str], Coroutine[object, object, None]]] = [
                search_tasks.run,
                status_loop.run,
            ]

            # Download enabled ⟺ the ``download`` section is present (``enabled: true``). Its loop
            # shares the catalog's stores and ``local_connection`` (one writer, on the event loop),
            # and the search session.
            download_config = crawler_config.download
            if download_config is not None:
                tracked_download_store = SqliteTrackedDownloadStore(local_connection)
                source_point_store = SqliteSourcePointStore(catalog_connection)
                download_labeler = DownloadLabeler(
                    observation_reader=observation_store,
                    decision_reader=decision_store,
                    tracked_download_reader=tracked_download_store,
                    targets=config.targets,
                )
                download_tracker = DownloadTracker(
                    tracked_download_writer=tracked_download_store,
                    tracked_download_reader=tracked_download_store,
                    download_labeler=download_labeler,
                    lost_after=download_config.lost_after,
                    wall_clock=wall_clock,
                    monotonic_clock=monotonic_clock,
                    observability_dispatcher=observability_dispatcher,
                    logger=StdlibLogger(DownloadTracker.__module__),
                )
                download_cycle = DownloadCycle(
                    download_client=client,
                    download_tracker=download_tracker,
                    download_decider=DownloadDecider(
                        free_space_meter=ShutilFreeSpaceMeter(download_config.output_directory),
                        min_free_bytes=download_config.min_free_bytes,
                        decision_reader=decision_store,
                        observation_reader=observation_store,
                        tracked_download_writer=tracked_download_store,
                        tracked_download_reader=tracked_download_store,
                        targets=config.targets,
                        download_tracker=download_tracker,
                        wall_clock=wall_clock,
                        observability_dispatcher=observability_dispatcher,
                        logger=StdlibLogger(DownloadDecider.__module__),
                    ),
                    download_starter=DownloadStarter(
                        download_client=client,
                        tracked_download_writer=tracked_download_store,
                        tracked_download_reader=tracked_download_store,
                        observation_reader=observation_store,
                        logger=StdlibLogger(DownloadStarter.__module__),
                    ),
                    source_watcher=SourceWatcher(
                        source_client=client,
                        tracked_download_reader=tracked_download_store,
                        source_point_writer=source_point_store,
                        source_point_reader=source_point_store,
                        download_labeler=download_labeler,
                        reappeared_after=download_config.reappeared_after,
                        sources_interval=download_config.sources_interval,
                        time_between_source_reads=download_config.time_between_source_reads,
                        wall_clock=wall_clock,
                        monotonic_clock=monotonic_clock,
                        observability_dispatcher=observability_dispatcher,
                        logger=StdlibLogger(SourceWatcher.__module__),
                    ),
                    logger=StdlibLogger(DownloadCycle.__module__),
                )
                download_loop = DownloadLoop(
                    download_cycle=download_cycle,
                    poll_interval_seconds=download_config.poll_interval_seconds,
                    monotonic_clock=monotonic_clock,
                    waker=waker,
                    run_state_reader=run_state_store,
                )
                loops.append(download_loop.run)

            crawler_lifecycle = CrawlerLifecycle(
                node_id_resolver=NodeIdResolver(
                    configured_node_id=crawler_config.node_id,
                    node_id_reader=node_id_store,
                    node_id_writer=node_id_store,
                    node_id_generator=Uuid4NodeIdGenerator(),
                    wall_clock=wall_clock,
                ),
                observability_dispatcher=observability_dispatcher,
                catalog_reevaluator=CatalogReevaluator(
                    policy_fingerprint=config.policy_fingerprint,
                    policy_fingerprint_reader=policy_fingerprint_store,
                    policy_fingerprint_writer=policy_fingerprint_store,
                    file_judge=file_judge,
                    catalog_scan_reader=catalog_scan_reader,
                    progress_every_files=_REEVALUATION_PROGRESS_EVERY_FILES,
                    logger=StdlibLogger(CatalogReevaluator.__module__),
                ),
                backoff=backoff,
                loops=loops,
                download_enabled=download_config is not None,
                loop_supervisor=LoopSupervisor(run_state_reader=run_state_store),
                logger=StdlibLogger(CrawlerLifecycle.__module__),
            )
            # Entered disarmed: the steady state is unbounded, and the run arms it as soon as the
            # shutdown is requested, so the unwind and the close below are bounded.
            async with asyncio.timeout(None) as shutdown_timeout:
                await crawler_lifecycle.run(
                    arm_shutdown_bound=lambda: shutdown_timeout.reschedule(
                        loop.time() + crawler_config.shutdown_deadline_seconds
                    ),
                )
                _print_progress("Workers stopped.")
                _print_progress(f"{len(workers)} amuled session(s) closing…")
                await stack.aclose()
                _print_progress("Databases closed: exiting.")
