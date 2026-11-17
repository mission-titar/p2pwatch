"""Composition root: loads the config, assembles the crawler it describes, then runs it.

COMPOSITION ring (the only one allowed to import adapters AND application). Builds:
- ONE ``SqliteObservationStore`` + ``SqliteCatalogScanReader``, ``SqliteDecisionStore``,
  ``SqliteNodeIdStore``, ``SqlitePolicyFingerprintStore``, ``SqliteBackoffStateStore`` and
  ``SqliteSearchStartStore``
  (each built once), connections opened by the ``SqliteDatabaseOpener``
  (migrations applied at startup, a failed one stopping the start).
- the ``MatchingEngine`` (once),
- ONE ``AmuleApiClient`` at a time on the one amuled the core drives, whose session every work
  over it shares, those works built by ``AmuleClientWorks``; ``AmuleClientRestartable`` rebuilds
  the client and its works when the ``RestartPolicy`` asks.
- ONE ``UvicornServerThread`` at a time serving the webui; ``WebuiRestartable`` rebuilds it and
  the watch over it when the ``RestartPolicy`` asks.

Works: one search per channel and keyword (``KeywordSearch``), the status watcher, download and
source tracking when configured, and the webui's thread watch, which ``CrawlerLifecycle`` runs
until ``PosixProcess`` or the webui requests the shutdown.
OBSERVABLE & BOUNDED shutdown (spec §6): long-lived resources are closed AFTER the full unwind of
the works (no worker can write anymore), all within ``shutdown_deadline_seconds``, what a fired
deadline leaves within ``CLOSE_TIMEOUT_SECONDS``.
"""

import asyncio
import ctypes
import logging
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path, PurePath

import apprise
import httpx

import p2pwatch.adapters.driving.webui
from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.asyncio_monotonic_clock import AsyncioMonotonicClock
from p2pwatch.adapters.driven.asyncio_run_state_store import AsyncioRunStateStore
from p2pwatch.adapters.driven.asyncio_waker import AsyncioWaker
from p2pwatch.adapters.driven.config.crawler_config import load_config
from p2pwatch.adapters.driven.glibc_memory_releaser import GlibcMemoryReleaser
from p2pwatch.adapters.driven.in_memory_node_metric_store import InMemoryNodeMetricStore
from p2pwatch.adapters.driven.in_memory_status_reading_store import InMemoryStatusReadingStore
from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.adapters.driven.persistence_sqlite.errors import OpeningInterruptedError
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
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    SqliteDatabaseOpener,
)
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
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_pre_migration_copier import (
    SqlitePreMigrationCopier,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_search_start_store import (
    SqliteSearchStartStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_source_reader import SqliteSourceReader
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_sql_executor import SqliteSqlExecutor
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.adapters.driven.random_jitter_generator import RandomJitterGenerator
from p2pwatch.adapters.driven.shutil_free_space_meter import ShutilFreeSpaceMeter
from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from p2pwatch.adapters.driven.threading_ticker import ThreadingTicker
from p2pwatch.adapters.driven.uuid4_node_id_generator import Uuid4NodeIdGenerator
from p2pwatch.adapters.driving.process.posix_process import PosixProcess
from p2pwatch.adapters.driving.webui.app import build_app as build_webui_app
from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.crawler_lifecycle import CrawlerLifecycle
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.ports.driving.crawler_runner import CrawlerRunner
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.node_id_resolver import NodeIdResolver
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.search_worker import SEARCH_BUDGET_SECONDS
from p2pwatch.application.steps.supervisor import ShutdownBoundArmer, Supervisor
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.application.use_cases.describe_file import DescribeFile
from p2pwatch.application.use_cases.describe_node import DescribeNode
from p2pwatch.application.use_cases.describe_source import DescribeSource
from p2pwatch.application.use_cases.describe_source_name import DescribeSourceName
from p2pwatch.application.use_cases.list_files import ListFiles
from p2pwatch.application.use_cases.list_node_metrics import ListNodeMetrics
from p2pwatch.application.use_cases.list_sources import ListSources
from p2pwatch.application.use_cases.request_shutdown import RequestShutdown
from p2pwatch.application.use_cases.run_console_query import RunConsoleQuery
from p2pwatch.application.use_cases.summarize_crawl import SummarizeCrawl
from p2pwatch.composition.amule_client_restartable import AmuleClientRestartable
from p2pwatch.composition.amule_client_works import AmuleClientWorks, DownloadSteps
from p2pwatch.composition.node_restart_policy import node_restart_policy
from p2pwatch.composition.restart_policy_built_later import RestartPolicyBuiltLater
from p2pwatch.composition.webui_restartable import WebuiRestartable, webui_thread_watch_over
from p2pwatch.composition.work_time_limits import AmuleWorkTimeLimits
from p2pwatch.domain.console_query import ConsoleDatabase
from p2pwatch.domain.crawler_config import CrawlerConfig, LoadedConfig
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.matching_read import MatchingExplainer
from p2pwatch.domain.search.keywords import dedupe_keywords
from p2pwatch.domain.shutdown_deadline_error import ShutdownDeadlineError
from p2pwatch.domain.work_components import webui_component

_logger = logging.getLogger(__name__)

# The label of the one client a node drives: crawler.yml has no key to name it.
_AMULE_CLIENT_NAME = ClientName("amuled")
_AMULE_API_TIMEOUT_SECONDS = 10.0
# httpx bounds each phase alone, so a server trickling its answer would hold a request for ever.
_AMULE_API_REQUEST_BOUND_SECONDS = 60.0
# Rows asked for per list request. Every list route caps at 100 when `limit` is omitted, which
# would silently truncate the shared-file sweep completion detection depends on (§7.5).
_AMULE_API_PAGE_SIZE = 500
# How often a search's progress is read: local traffic with our own daemon.
_AMULE_API_PROGRESS_POLL_INTERVAL = timedelta(seconds=5)
_WEBUI_START_TIMEOUT_SECONDS = 5.0
# uvicorn polls ``should_exit`` every 0.1 s, so the join normally returns well within its bound.
_WEBUI_JOIN_TIMEOUT_SECONDS = 5.0
# How many SQLite VM steps the SQL console runs between two checks of its query budget.
_CONSOLE_BUDGET_CHECK_INSTRUCTIONS = 1000
# A longer filename is never matched: it bounds the matching's cost on what a peer advertises.
_MAX_FILENAME_LENGTH = 4096
# The close left once the shutdown deadline fired: the webui's join, the logout, the databases.
CLOSE_TIMEOUT_SECONDS = 5.0
# One INFO progress line per this many files, so a long sweep visibly advances.
_REEVALUATION_PROGRESS_EVERY_FILES = 200


def _print_progress(message: str) -> None:
    """Human shutdown line on stderr (spec §6: observable progress, outside logging)."""
    print(message, file=sys.stderr, flush=True)


@asynccontextmanager
async def resource_stack(*, close_timeout_seconds: float) -> AsyncIterator[AsyncExitStack]:
    """The stack of the resources the crawler holds, closed on exit, the close cut past
    ``close_timeout_seconds``, what is left then closed by the process's exit."""
    resources = AsyncExitStack()
    try:
        yield resources
    finally:
        # Best effort after a fired deadline or a failed setup: its failures never mask the first.
        with suppress(BaseException):
            async with asyncio.timeout(close_timeout_seconds):
                await resources.aclose()


@asynccontextmanager
async def shutdown_bound(*, deadline_seconds: float) -> AsyncIterator[ShutdownBoundArmer]:
    """Unbounded until armed, then cut ``deadline_seconds`` later by ``ShutdownDeadlineError``;
    a ``TimeoutError`` raised in its body passes through as it is."""
    loop = asyncio.get_running_loop()
    try:
        async with asyncio.timeout(None) as timeout:
            yield lambda: timeout.reschedule(loop.time() + deadline_seconds)
    except TimeoutError as error:
        if not timeout.expired():
            raise
        raise ShutdownDeadlineError(f"cut after {deadline_seconds:g} s") from error


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
        self,
        crawler_config: CrawlerConfig,
        *,
        monotonic_clock: MonotonicClock,
        wall_clock: WallClock,
        search_start_store: SqliteSearchStartStore,
    ) -> AmuleApiClient:
        """The node's one session on amuled, spacing its first searches from the latest starts
        ``search_start_store`` kept, the previous run's included."""
        host, port = self._amule_api_address
        return AmuleApiClient(
            host,
            client_name=_AMULE_CLIENT_NAME,
            port=port,
            password=crawler_config.amule_api_password,
            timeout_seconds=_AMULE_API_TIMEOUT_SECONDS,
            request_bound_seconds=_AMULE_API_REQUEST_BOUND_SECONDS,
            page_size=_AMULE_API_PAGE_SIZE,
            progress_poll_interval=_AMULE_API_PROGRESS_POLL_INTERVAL,
            monotonic_clock=monotonic_clock,
            wall_clock=wall_clock,
            search_start_writer=search_start_store,
            search_start_reader=search_start_store,
            transport_factory=httpx.AsyncHTTPTransport,
        )

    def _webui_thread(
        self,
        *,
        config: LoadedConfig,
        status_reading_store: InMemoryStatusReadingStore,
        node_metric_store: InMemoryNodeMetricStore,
        shutdown_requester: RequestShutdown,
        engine: MatchingEngine,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        database_opener: SqliteDatabaseOpener,
    ) -> UvicornServerThread:
        """The read-only webui on its OWN thread + loop (spec §5), not started yet. It shares with
        the crawler the parsed config (immutable), the engine and the clocks (no state after their
        construction), the status reading and node metric stores (whole snapshots swapped, never
        mutated) and the run state (every change scheduled on the crawler's loop).
        It reads through its OWN ``ThreadReadConnections``, one connection per thread, each opened
        by ``database_opener``."""
        crawler_config = config.crawler_config
        webui_package_directory = Path(p2pwatch.adapters.driving.webui.__file__).parent
        local_db_path = Path(crawler_config.local_db_path)
        catalog_db_path = Path(crawler_config.catalog_db_path)
        local_read_connections = ThreadReadConnections(
            local_db_path, open_reader=database_opener.open_reader
        )
        node_state_reader = SqliteNodeStateReader(local_read_connections)
        catalog_read_connections = ThreadReadConnections(
            catalog_db_path, open_reader=database_opener.open_reader
        )
        catalog_file_reader = SqliteCatalogFileReader(catalog_read_connections)
        source_reader = SqliteSourceReader(catalog_read_connections)
        app = build_webui_app(
            target_segments=config.targets,
            templates_directory=webui_package_directory / "templates",
            static_directory=webui_package_directory / "static",
            shutdown_requester=shutdown_requester,
            crawl_summarizer=SummarizeCrawl(
                target_ids=tuple(target.target_id for target in config.targets),
                coverage_reader=SqliteCoverageReader(catalog_read_connections),
                node_state_reader=node_state_reader,
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
                        catalog_db_path,
                        open_reader=database_opener.open_reader,
                        monotonic_clock=monotonic_clock,
                        budget_check_instructions=_CONSOLE_BUDGET_CHECK_INSTRUCTIONS,
                    ),
                    ConsoleDatabase.LOCAL: SqliteSqlExecutor(
                        local_db_path,
                        open_reader=database_opener.open_reader,
                        monotonic_clock=monotonic_clock,
                        budget_check_instructions=_CONSOLE_BUDGET_CHECK_INSTRUCTIONS,
                    ),
                }
            ),
            node_metric_lister=ListNodeMetrics(node_metric_store),
            amule_url=crawler_config.webui.amule_url,
        )
        return UvicornServerThread(
            app,
            address=self._webui_address,
            start_timeout_seconds=_WEBUI_START_TIMEOUT_SECONDS,
            join_timeout_seconds=_WEBUI_JOIN_TIMEOUT_SECONDS,
            serving_resources=(catalog_read_connections, local_read_connections),
        )

    async def run_crawler(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        """Opens the resources under ``PosixProcess``, runs ``CrawlerLifecycle`` to shutdown (§6).

        Only the shutdown is bounded: an overrun raises ``ShutdownDeadlineError``, and the resource
        stack then closes what is left, before ``PosixProcess`` gives the signals back.
        """
        config = load_config(
            Path(config_path),
            targets_path=Path(targets_path),
            matcher_path=Path(matcher_path),
            env=self._env,
        )
        crawler_config = config.crawler_config
        self._root_logger.setLevel(crawler_config.observability.log_level)
        # Startup version line (spec 2026-07-10-git-driven-versioning): the number baked into the
        # installed wheel by the build (setuptools-scm / SETUPTOOLS_SCM_PRETEND_VERSION), so an
        # operator can correlate a running node to a release.
        _logger.info("p2pwatch version %s", version("p2pwatch"))
        wall_clock = SystemWallClock()
        monotonic_clock = AsyncioMonotonicClock()
        waker = AsyncioWaker()
        # On the crawler's OWN loop, so the webui thread changes it thread-safely.
        run_state_store = AsyncioRunStateStore(loop=asyncio.get_running_loop())
        shutdown_requester = RequestShutdown(run_state_store)
        # The last context exits first: the resources close, then the signal handlers go.
        async with (
            PosixProcess(shutdown_requester) as process,
            resource_stack(close_timeout_seconds=CLOSE_TIMEOUT_SECONDS) as stack,
        ):
            ticker = ThreadingTicker(monotonic_clock)
            database_opener = SqliteDatabaseOpener(
                SqlitePreMigrationCopier(
                    wall_clock,
                    ticker=ticker,
                    free_bytes=lambda directory: ShutilFreeSpaceMeter(directory).free_bytes(),
                ),
                ticker=ticker,
                free_bytes=lambda directory: ShutilFreeSpaceMeter(directory).free_bytes(),
                # None: the process's own symbols, the C library's included.
                memory_releaser=GlibcMemoryReleaser(ctypes.CDLL(None)),
                is_shutdown_requested=process.is_signalled,
            )
            try:
                catalog_connection = database_opener.open_catalog(
                    Path(crawler_config.catalog_db_path)
                )
                stack.callback(catalog_connection.close)
                local_connection = database_opener.open_local(Path(crawler_config.local_db_path))
                stack.callback(local_connection.close)
            except OpeningInterruptedError as interruption:
                _print_progress(f"Shutdown requested during the start: {interruption}; exiting.")
                return

            node_id_store = SqliteNodeIdStore(local_connection)
            # Before the client logs in: a node whose password amuled refuses keeps its id.
            node_id = NodeIdResolver(
                node_id_reader=node_id_store,
                node_id_writer=node_id_store,
                node_id_generator=Uuid4NodeIdGenerator(),
                wall_clock=wall_clock,
            ).resolve()
            policy_fingerprint_store = SqlitePolicyFingerprintStore(local_connection)
            observability = crawler_config.observability
            node_metric_store = InMemoryNodeMetricStore()
            notifier = AppriseNotifier(
                tuple((t.url, t.audience, t.node_prefix) for t in observability.notifications),
                apprise_factory=apprise.Apprise,
            )
            observability_dispatcher = ObservabilityDispatcher(
                logger=StdlibLogger(ObservabilityDispatcher.__module__),
                node_metric_writer=node_metric_store,
                notifier=notifier,
                notification_timeout_seconds=observability.notification_timeout_seconds,
            )
            observation_store = SqliteObservationStore(catalog_connection)
            catalog_scan_reader = SqliteCatalogScanReader(catalog_connection)
            decision_store = SqliteDecisionStore(catalog_connection)
            backoff_state_store = SqliteBackoffStateStore(local_connection)
            engine = MatchingEngine(
                config.matcher_config,
                targets=config.targets,
                max_filename_length=_MAX_FILENAME_LENGTH,
            )
            status_reading_store = InMemoryStatusReadingStore((_AMULE_CLIENT_NAME,))
            # In-process webui (spec §5): own thread + loop, started EARLY (before the daemon client
            # + startup re-evaluation) so it is up promptly and stays isolated from the crawler's
            # synchronous work. A crash degrades (spec §17.1), and its watch has it rebuilt.

            def build_webui_thread() -> UvicornServerThread:
                return self._webui_thread(
                    config=config,
                    status_reading_store=status_reading_store,
                    node_metric_store=node_metric_store,
                    shutdown_requester=shutdown_requester,
                    engine=engine,
                    wall_clock=wall_clock,
                    monotonic_clock=monotonic_clock,
                    database_opener=database_opener,
                )

            webui_part = webui_component()

            def webui_works_over(thread: UvicornServerThread) -> Sequence[SupervisedWork]:
                return webui_thread_watch_over(
                    thread, component=webui_part, monotonic_clock=monotonic_clock
                )

            webui_thread = build_webui_thread()
            webui = WebuiRestartable(
                webui_thread, build_thread=build_webui_thread, works_over=webui_works_over
            )
            # The thread held then, stopped at the unwind before the database connections close.
            stack.push_async_callback(webui.close)
            await webui_thread.start()
            # SHARED backoff registry: built ONCE, resumes its waits at the lifecycle's start
            # (backoff survives restart, spec §3/§7), injected into ALL workers + the saver the
            # searches share. Single writer on the event loop.
            backoff = BackoffRegistry(
                _backoff_policy(crawler_config),
                wall_clock=wall_clock,
                monotonic_clock=monotonic_clock,
                jitter_generator=RandomJitterGenerator(
                    jitter_seed=None
                ),  # seeded by the system's entropy
                backoff_state_reader=backoff_state_store,
            )
            file_judge = FileJudge(
                observation_reader=observation_store,
                decision_writer=decision_store,
                decision_reader=decision_store,
                engine=engine,
                waker=waker,
                observability_dispatcher=observability_dispatcher,
                wall_clock=wall_clock,
                node_id=node_id,
            )
            cataloguer = Cataloguer(
                observation_writer=observation_store,
                file_judge=file_judge,
                observability_dispatcher=observability_dispatcher,
                wall_clock=wall_clock,
                node_id=node_id,
                logger=StdlibLogger(Cataloguer.__module__),
            )
            search_start_store = SqliteSearchStartStore(local_connection)

            def build_client() -> AmuleApiClient:
                return self._amule_api_client(
                    crawler_config,
                    monotonic_clock=monotonic_clock,
                    wall_clock=wall_clock,
                    search_start_store=search_start_store,
                )

            client = build_client()
            # Download enabled ⟺ the ``download`` section is present (``enabled: true``).
            download_config = crawler_config.download
            # Set once the works are built: they record on the node's health, the policy maps them.
            restart_policy = RestartPolicyBuiltLater()
            node_health = NodeHealth(
                logger=StdlibLogger(NodeHealth.__module__),
                subscribers=(
                    HealthAlerter(
                        observability_dispatcher=observability_dispatcher,
                        node_id=node_id,
                        min_free_bytes=(
                            None if download_config is None else download_config.min_free_bytes
                        ),
                    ).send,
                    restart_policy,
                ),
            )
            client_works = AmuleClientWorks(
                client_name=_AMULE_CLIENT_NAME,
                channels=client.channels(),
                keywords=crawler_config.search.keywords,
                download_steps=(
                    None
                    if download_config is None
                    else DownloadSteps(
                        download_config,
                        client_name=_AMULE_CLIENT_NAME,
                        targets=config.targets,
                        local_connection=local_connection,
                        catalog_connection=catalog_connection,
                        observation_store=observation_store,
                        decision_store=decision_store,
                        waker=waker,
                        wall_clock=wall_clock,
                        monotonic_clock=monotonic_clock,
                        observability_dispatcher=observability_dispatcher,
                        node_health=node_health,
                        node_id=node_id,
                    )
                ),
                backoff=backoff,
                backoff_saver=BackoffSaver(
                    backoff=backoff,
                    backoff_state_writer=backoff_state_store,
                    logger=StdlibLogger(BackoffSaver.__module__),
                ),
                cataloguer=cataloguer,
                status_reading_writer=status_reading_store,
                node_health=node_health,
                observability_dispatcher=observability_dispatcher,
                wall_clock=wall_clock,
                monotonic_clock=monotonic_clock,
                time_limits=AmuleWorkTimeLimits(
                    request_bound=client.request_bound,
                    search_budget=timedelta(seconds=SEARCH_BUDGET_SECONDS),
                    notification_timeout=timedelta(
                        seconds=observability.notification_timeout_seconds
                    ),
                    keywords=dedupe_keywords(crawler_config.search.keywords),
                ),
            )
            amule_client = AmuleClientRestartable(
                client,
                client_name=_AMULE_CLIENT_NAME,
                build_client=build_client,
                works_over=client_works.over,
            )
            # The client held then, not this first one, which a rebuild replaces.
            stack.push_async_callback(amule_client.close)
            await client.open()
            works_of = {
                amule_client: client_works.over(client),
                webui: webui_works_over(webui_thread),
            }
            works = [supervised for works in works_of.values() for supervised in works]
            for supervised in works:
                seconds = supervised.time_limit.total_seconds()
                _logger.debug("%s: time limit %g s", supervised.work, seconds)
                parts = ", ".join(component.name for component in supervised.components)
                _logger.debug("%s: turns recorded on %s", supervised.work, parts)
            supervisor = Supervisor(
                run_state_reader=run_state_store,
                monotonic_clock=monotonic_clock,
                node_health=node_health,
                logger=StdlibLogger(Supervisor.__module__),
            )
            restart_policy.set(node_restart_policy(works_of, supervisor=supervisor))
            crawler_lifecycle = CrawlerLifecycle(
                node_id=node_id,
                observability_dispatcher=observability_dispatcher,
                catalog_reevaluator=CatalogReevaluator(
                    policy_fingerprint=config.policy_fingerprint,
                    policy_fingerprint_reader=policy_fingerprint_store,
                    policy_fingerprint_writer=policy_fingerprint_store,
                    file_judge=file_judge,
                    catalog_scan_reader=catalog_scan_reader,
                    progress_every_files=_REEVALUATION_PROGRESS_EVERY_FILES,
                    run_state_reader=run_state_store,
                    monotonic_clock=monotonic_clock,
                    logger=StdlibLogger(CatalogReevaluator.__module__),
                ),
                backoff=backoff,
                works=works,
                download_enabled=download_config is not None,
                supervisor=supervisor,
                logger=StdlibLogger(CrawlerLifecycle.__module__),
            )
            # Entered disarmed: the steady state is unbounded, and the run arms it as soon as the
            # shutdown is requested, so the unwind and the close below are bounded.
            async with shutdown_bound(
                deadline_seconds=crawler_config.shutdown_deadline_seconds
            ) as arm_shutdown_bound:
                await crawler_lifecycle.run(arm_shutdown_bound=arm_shutdown_bound)
                _print_progress("Workers stopped.")
                _print_progress("amuled session closing…")
                await stack.aclose()
                _print_progress("Databases closed: exiting.")
