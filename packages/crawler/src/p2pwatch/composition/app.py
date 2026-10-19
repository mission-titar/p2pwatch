"""Composition root: loads the config, assembles the crawler it describes, then runs it.

COMPOSITION layer (the only one allowed to import adapters AND application). Builds:
- ONE ``SqliteCatalogRepository`` + ONE ``SqliteLocalStateRepository`` +
  ``SqliteBackoffStateRepository`` (single writer, invariant §11), connections opened
  via ``open_catalog``/``open_local`` (migrations checked at startup, fail-fast §14).
- the ``MatchingEngine`` (once),
- ONE ``AmuleApiClient`` + ``SearchWorker`` on the one amuled the core drives, whose
  session the status and download loops share.

Loops: the search tasks (``SearchTaskRunner``), the status loop, and the download loop when
configured, which ``RunCrawler`` runs until ``PosixProcess`` or the webui requests the shutdown.
OBSERVABLE & BOUNDED shutdown (spec §6): long-lived resources are closed AFTER the full unwind of
the loops (no worker can write anymore), all within ``shutdown_deadline_seconds``.
"""

import asyncio
import logging
import sys
from collections.abc import Callable, Coroutine, Mapping
from contextlib import AsyncExitStack
from functools import partial
from importlib.metadata import version
from pathlib import Path, PurePath

from prometheus_client import CollectorRegistry

import p2pwatch.adapters.driving.webui
from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.asyncio_run_state import AsyncioRunState
from p2pwatch.adapters.driven.config.crawler_config import (
    AMULE_CLIENT_NAME,
    CrawlerConfig,
    LoadedConfig,
    load_config,
)
from p2pwatch.adapters.driven.disk_space_shutil import ShutilDiskSpace
from p2pwatch.adapters.driven.monotonic_clock_asyncio import AsyncioMonotonicClock
from p2pwatch.adapters.driven.mule_api.client import AmuleApiClient
from p2pwatch.adapters.driven.observability.apprise_notifier import AppriseNotifier
from p2pwatch.adapters.driven.observability.dispatcher import ObservabilityDispatcher
from p2pwatch.adapters.driven.observability.prometheus_sink import (
    PrometheusSink,
    start_metrics_server,
)
from p2pwatch.adapters.driven.persistence_sqlite.backoff_state_repository import (
    SqliteBackoffStateRepository,
)
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog, open_local
from p2pwatch.adapters.driven.persistence_sqlite.download_repository import SqliteDownloadRepository
from p2pwatch.adapters.driven.persistence_sqlite.local_state_repository import (
    SqliteLocalStateRepository,
)
from p2pwatch.adapters.driven.persistence_sqlite.source_repository import SqliteSourceRepository
from p2pwatch.adapters.driven.rng_random import SeededRng
from p2pwatch.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch.adapters.driven.uuid4_node_id_generator import Uuid4NodeIdGenerator
from p2pwatch.adapters.driven.wake_hub_asyncio import AsyncioWakeHub
from p2pwatch.adapters.driven.wall_clock_system import SystemWallClock
from p2pwatch.adapters.driving.process.posix_process import PosixProcess
from p2pwatch.adapters.driving.webui.app import build_app as build_webui_app
from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.reevaluate_catalog import reevaluate_catalog
from p2pwatch.application.run_crawler import RunCrawler
from p2pwatch.application.run_download_cycle import (
    DownloadLoopDeps,
    download_loop,
)
from p2pwatch.application.search_tasks import SearchTaskRunner
from p2pwatch.application.search_worker import (
    BackoffPolicy,
    BackoffRegistry,
    SearchWorker,
    WorkerDeps,
)
from p2pwatch.application.status_loop import StatusBoard, StatusLoopDeps, status_loop
from p2pwatch.ports.driven.clock import MonotonicClock, WallClock
from p2pwatch.ports.driving.crawler_control import CrawlerControl
from p2pwatch.ports.driving.crawler_runner import CrawlerRunner

_logger = logging.getLogger("p2pwatch.composition.app")


def _print_progress(message: str) -> None:
    """Human shutdown line on stderr (spec §6: observable progress, outside logging)."""
    print(message, file=sys.stderr, flush=True)


def _backoff_policy(config: CrawlerConfig) -> BackoffPolicy:
    """Unpacks the backoff config into primitives for the application (dependency rule)."""
    backoff = config.search.backoff
    return BackoffPolicy(
        base_seconds=backoff.base_seconds,
        cap_seconds=backoff.cap_seconds,
        factor=backoff.factor,
        jitter_ratio=backoff.jitter_ratio,
    )


class CrawlerApp(CrawlerRunner):
    """Loads the config, then assembles and runs the crawler it describes (composition root)."""

    def __init__(
        self,
        *,
        webui_address: tuple[str, int],
        amule_api_address: tuple[str, int],
        env: Mapping[str, str],
    ) -> None:
        self._webui_address = webui_address
        self._amule_api_address = amule_api_address
        self._env = env

    def _amule_api_client(
        self, crawler_config: CrawlerConfig, monotonic_clock: MonotonicClock
    ) -> AmuleApiClient:
        """The node's one session on amuled, paced on the composition's monotonic clock."""
        host, port = self._amule_api_address
        return AmuleApiClient(
            host, port, crawler_config.amule_api_password, monotonic_clock=monotonic_clock
        )

    async def _start_webui(
        self,
        *,
        config: LoadedConfig,
        stack: AsyncExitStack,
        status_board: StatusBoard,
        control: CrawlerControl,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
    ) -> None:
        """Start the read-only webui on its OWN thread + loop (spec §5), sharing only IMMUTABLE
        state with the crawler (the parsed matcher/targets, the DB paths). It reads through its
        OWN ``ReaderProvider`` (inside ``build_webui_app``); nothing here touches the crawler's
        event loop nor its writer connections. Its stop is registered on ``stack`` so it runs
        during the normal LIFO unwind at shutdown, AFTER the loops are stopped."""
        crawler_config = config.crawler_config
        webui_pkg_dir = Path(p2pwatch.adapters.driving.webui.__file__).parent
        app = build_webui_app(
            catalog_db_path=Path(crawler_config.catalog_db_path),
            local_db_path=Path(crawler_config.local_db_path),
            matcher_config=config.matcher_config,
            target_segments=config.targets,
            templates_dir=webui_pkg_dir / "templates",
            static_dir=webui_pkg_dir / "static",
            control=control,
            status_readings=status_board,
            amule_url=crawler_config.webui.amule_url,
            wall_clock=wall_clock,
            monotonic_clock=monotonic_clock,
            source_period_gap=crawler_config.webui.source_period_gap,
        )
        server_thread = UvicornServerThread(app, self._webui_address)
        stack.push_async_callback(server_thread.stop)
        await server_thread.start()

    async def crawl(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        """Opens the resources under ``PosixProcess``, runs ``RunCrawler`` until the shutdown (§6).

        Only the shutdown is bounded: an overrun raises ``TimeoutError``, and ``PosixProcess``
        then closes what is left.
        """
        config = load_config(Path(config_path), Path(targets_path), Path(matcher_path), self._env)
        crawler_config = config.crawler_config
        logging.getLogger().setLevel(crawler_config.observability.log_level)
        # Startup version line (spec 2026-07-10-git-driven-versioning): the number baked into the
        # installed wheel by the build (setuptools-scm / SETUPTOOLS_SCM_PRETEND_VERSION), so an
        # operator can correlate a running node to a release.
        _logger.info("p2pwatch version %s", version("p2pwatch"))
        wall_clock = SystemWallClock()
        monotonic_clock = AsyncioMonotonicClock()
        wake_hub = AsyncioWakeHub()
        shutdown = asyncio.Event()
        # The pause gate, armed (set = un-paused) so the crawler starts running.
        resumed = asyncio.Event()
        resumed.set()
        loop = asyncio.get_running_loop()
        # On the crawler's OWN loop + events, so the webui thread changes it thread-safely.
        run_state = AsyncioRunState(loop=loop, resumed=resumed, shutdown=shutdown)
        async with PosixProcess(run_state) as stack:
            catalog_conn = open_catalog(crawler_config.catalog_db_path)
            stack.callback(catalog_conn.close)
            local_conn = open_local(crawler_config.local_db_path)
            stack.callback(local_conn.close)

            local_repo = SqliteLocalStateRepository(local_conn)
            observability = crawler_config.observability
            registry = CollectorRegistry()
            notifier = AppriseNotifier(
                tuple((t.url, t.audience, t.node_prefix) for t in observability.notifications)
            )
            telemetry = ObservabilityDispatcher(
                metrics=PrometheusSink(registry),
                notifier=notifier,
                notification_timeout_seconds=observability.notification_timeout_seconds,
            )
            stack.callback(start_metrics_server(registry, observability.metrics_port))
            catalog_repo = SqliteCatalogRepository(catalog_conn)
            backoff_states = SqliteBackoffStateRepository(local_conn)
            engine = MatchingEngine(config.matcher_config, config.targets)
            board = StatusBoard((AMULE_CLIENT_NAME,), monotonic_clock)
            # In-process webui (spec §5): own thread + loop, started EARLY (before the daemon client
            # + startup re-evaluation) so it is up promptly and stays isolated from the crawler's
            # synchronous work. Gated by ``webui.enabled``; a crash degrades (spec §17.1). Its
            # graceful stop is on ``stack`` → runs at the normal shutdown unwind (after DB conns
            # are pushed, so it stops the thread before those close during LIFO teardown).
            if crawler_config.webui.enabled:
                await self._start_webui(
                    config=config,
                    stack=stack,
                    status_board=board,
                    control=run_state,
                    wall_clock=wall_clock,
                    monotonic_clock=monotonic_clock,
                )
            # SHARED backoff registry: built ONCE, RELOADED from backoff_states
            # (backoff survives restart, spec §3/§7), injected into ALL workers
            # + passed to the search tasks that persist it. Single writer on the event loop.
            backoff = BackoffRegistry(
                _backoff_policy(crawler_config), wall_clock, monotonic_clock, SeededRng()
            )
            backoff.load_from(backoff_states.load_backoff_states())
            deps = WorkerDeps(
                catalog=catalog_repo,
                engine=engine,
                wake_hub=wake_hub,
                backoff=backoff,
                telemetry=telemetry,
                wall_clock=wall_clock,
                logger=StdlibLogger("p2pwatch.application.search_worker"),
                observation_logger=StdlibLogger("p2pwatch.application.record_observations"),
            )

            client = self._amule_api_client(crawler_config, monotonic_clock)
            stack.push_async_callback(client.close)
            await client.open()
            workers = [SearchWorker(AMULE_CLIENT_NAME, client, deps)]
            # The status and download loops share the search session: one session per node.
            status_deps = StatusLoopDeps(
                AMULE_CLIENT_NAME, client, wall_clock, monotonic_clock, telemetry, shutdown, board
            )
            search_tasks = SearchTaskRunner(
                workers=workers,
                keywords=crawler_config.search.keywords,
                resumed=resumed,
                backoff=backoff,
                backoff_states=backoff_states,
                monotonic_clock=monotonic_clock,
                logger=StdlibLogger("p2pwatch.application.search_tasks"),
            )
            loops: list[Callable[[str], Coroutine[object, object, None]]] = [
                search_tasks.run,
                partial(status_loop, status_deps),
            ]

            # Download enabled ⟺ the ``download`` section is present (``enabled: true``). Its loop
            # shares the catalog's repos and ``local_conn`` (one writer, on the event loop), and
            # the search session.
            download_config = crawler_config.download
            if download_config is not None:
                download_deps = DownloadLoopDeps(
                    download_client=client,
                    source_client=client,
                    downloads=SqliteDownloadRepository(local_conn),
                    sources=SqliteSourceRepository(
                        catalog_conn, download_config.time_between_source_reads
                    ),
                    catalog=catalog_repo,
                    targets=config.targets,
                    disk=ShutilDiskSpace(download_config.output_dir),
                    min_free_bytes=download_config.min_free_bytes,
                    lost_after=download_config.lost_after,
                    poll_interval_seconds=download_config.poll_interval_seconds,
                    reappeared_after=download_config.reappeared_after,
                    sources_interval=download_config.sources_interval,
                    wall_clock=wall_clock,
                    monotonic_clock=monotonic_clock,
                    telemetry=telemetry,
                    logger=StdlibLogger("p2pwatch.application.run_download_cycle"),
                    wake_hub=wake_hub,
                    shutdown=shutdown,
                )
                loops.append(partial(download_loop, download_deps))

            run_crawler = RunCrawler(
                configured_node_id=crawler_config.node_id,
                node_id_reader=local_repo,
                node_id_writer=local_repo,
                node_id_generator=Uuid4NodeIdGenerator(),
                wall_clock=wall_clock,
                telemetry=telemetry,
                policy_fingerprint=config.policy_fingerprint,
                local_state=local_repo,
                reevaluate=lambda node_id: reevaluate_catalog(
                    catalog=catalog_repo,
                    engine=engine,
                    wake_hub=wake_hub,
                    telemetry=telemetry,
                    wall_clock=wall_clock,
                    logger=StdlibLogger("p2pwatch.application.reevaluate_catalog"),
                    node_id=node_id,
                ),
                loops=loops,
                download_enabled=download_config is not None,
                shutdown=shutdown,
                logger=StdlibLogger("p2pwatch.application.run_crawler"),
                reevaluation_gate_logger=StdlibLogger(
                    "p2pwatch.application.reevaluate_if_policy_changed"
                ),
            )
            # Entered disarmed: the steady state is unbounded, and the run arms it as soon as the
            # shutdown is requested, so the unwind and the close below are bounded.
            async with asyncio.timeout(None) as shutdown_timeout:
                await run_crawler.run(
                    arm_shutdown_bound=lambda: shutdown_timeout.reschedule(
                        loop.time() + crawler_config.shutdown_deadline_seconds
                    ),
                )
                _print_progress("Workers stopped.")
                _print_progress(f"{len(workers)} amuled session(s) closing…")
                await stack.aclose()
                _print_progress("Databases closed: exiting.")
