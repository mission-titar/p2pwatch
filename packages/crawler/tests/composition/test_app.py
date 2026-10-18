import asyncio
import json
import logging
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette

from catalog_matching.config import MatcherConfig
from catalog_matching.models import TargetSegment
from catalog_matching.validation import parse_matcher_config
from p2pwatch.adapters.config.crawler_config import (
    AMULE_CLIENT_NAME,
    AmuleEndpoint,
    BackoffConfig,
    CrawlerConfig,
    DownloadConfig,
    SearchConfig,
    WebuiConfig,
)
from p2pwatch.adapters.config.yaml_loader import load_yaml
from p2pwatch.adapters.mule_api.client import AmuleApiClient
from p2pwatch.adapters.persistence_sqlite.backoff_state_repository import (
    SqliteBackoffStateRepository,
)
from p2pwatch.adapters.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.persistence_sqlite.connection import open_catalog, open_local, utc_iso
from p2pwatch.adapters.persistence_sqlite.download_repository import SqliteDownloadRepository
from p2pwatch.adapters.persistence_sqlite.local_state_repository import (
    SqliteLocalStateRepository,
)
from p2pwatch.adapters.persistence_sqlite.source_repository import SqliteSourceRepository
from p2pwatch.application.run_download_cycle import DownloadLoopDeps
from p2pwatch.composition import app as composition_app
from p2pwatch.composition.app import (
    CrawlerApp,
    default_download_client_factory,
    default_mule_client_factory,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation
from p2pwatch.domain.source import SourceKey, SourceReading, SourceRole
from p2pwatch.ports.backoff_state_repository import BackoffKey, BackoffState
from p2pwatch.ports.client_status import ClientStatus
from p2pwatch.ports.clock import MonotonicClock, MonotonicInstant
from p2pwatch.ports.download_client import DownloadRequest, DownloadStatus
from p2pwatch.ports.search_client import SearchAnswer
from p2pwatch_testing.adapters.mule_api.api_fakes import PASSWORD, FakeAmuleApi
from p2pwatch_testing.application.fakes import (
    FakeMonotonicClock,
    FakeMuleClient,
    FakeTime,
    RecordingWakeHub,
)
from p2pwatch_testing.catalog_rows import insert_file, observation_node_ids
from p2pwatch_testing.virtual_time import (
    MONOTONIC_EPOCH,
    LoopMonotonicClock,
    LoopWallClock,
    run_virtual,
)

_TARGETS = (
    TargetSegment(
        season=2,
        seasonal_number=11,
        absolute_number=62,
        letter="A",
        title="Les demoiselles cambrioleuses",
    ),
)
_MATCHER = Path(__file__).resolve().parents[4] / "deploy" / "matcher.yml"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
# Arbitrary policy fingerprint for tests that do not exercise the re-evaluation gate itself
# (Task 6 tests below construct their OWN fingerprint to drive the "ran"/"skipped" branches).
_FP = "test-policy-fingerprint"
# Off by default; the webui tests below turn it on, served on a free loopback port.
_WEBUI_OFF = WebuiConfig(enabled=False)
_WEBUI_ADDRESS = ("127.0.0.1", 0)
_WEBUI_LOGGER = "p2pwatch.webui.composition.uvicorn_server_thread"
# The client factories below never connect to it.
_AMULE_API_ADDRESS = ("ed2k", 4711)


class _NoopRng:
    """Zero jitter (test determinism)."""

    def jitter(self, span: float) -> float:
        return 0.0


@pytest.fixture
def matcher_config() -> MatcherConfig:
    return parse_matcher_config(load_yaml(_MATCHER))


def _crawler_config(
    tmp_path: Path,
    shutdown_deadline: float = 30.0,
    *,
    keywords: tuple[str, ...] = ("keroro", "titar"),
    node_id: str | None = None,
    download: DownloadConfig | None = None,
    webui: WebuiConfig = _WEBUI_OFF,
) -> CrawlerConfig:
    return CrawlerConfig(
        search=SearchConfig(
            keywords=keywords,
            backoff=BackoffConfig(base_seconds=2.0, cap_seconds=60.0, factor=2.0, jitter_ratio=0.0),
        ),
        shutdown_deadline_seconds=shutdown_deadline,
        amule_api_password="p",
        catalog_db_path=str(tmp_path / "catalog.db"),
        local_db_path=str(tmp_path / "local.db"),
        node_id=node_id,
        download=download,
        webui=webui,
    )


def _download_config(tmp_path: Path) -> DownloadConfig:
    return DownloadConfig(
        poll_interval_seconds=30.0,
        min_free_bytes=1_000_000_000,
        lost_after=timedelta(hours=24),
        output_dir=str(tmp_path),
        reappeared_after=timedelta(hours=12),
        sources_interval=timedelta(minutes=5),
    )


def _full_crawler_config(tmp_path: Path) -> CrawlerConfig:
    """FULL-mode config: ``download`` section present (enabled)."""
    return _crawler_config(tmp_path, download=_download_config(tmp_path))


def _make_app(
    tmp_path: Path,
    matcher_config: MatcherConfig,
    *,
    factory: object,
    node_id: str | None = None,
    shutdown_deadline: float = 30.0,
) -> CrawlerApp:
    return CrawlerApp(
        crawler_config=_crawler_config(tmp_path, shutdown_deadline, node_id=node_id),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=factory,  # type: ignore[arg-type]
    )


class _ShutdownOnStatusClient(FakeMuleClient):
    """Client that triggers app shutdown on the status loop's FIRST reading."""

    def __init__(
        self,
        app_holder: dict[str, CrawlerApp],
        results: list[tuple[FileObservation, ...]] | None = None,
    ) -> None:
        super().__init__(results=results)
        self._app_holder = app_holder
        self._fired = False

    async def status(self) -> ClientStatus:
        if not self._fired:
            self._fired = True
            self._app_holder["app"]._shutdown.set()  # request the shutdown once the loops run
        return await super().status()


@pytest.mark.asyncio
async def test_app_runs_then_shuts_down_cleanly(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    created: list[_ShutdownOnStatusClient] = []
    app_holder: dict[str, CrawlerApp] = {}

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        client = _ShutdownOnStatusClient(app_holder)
        created.append(client)
        return client

    app = _make_app(tmp_path, matcher_config, factory=factory)
    app_holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    assert created and created[0].close_calls == 1  # client closed AFTER the unwind
    assert created[0].connect_calls >= 1  # connected at setup
    assert (tmp_path / "catalog.db").exists()
    assert (tmp_path / "local.db").exists()


@pytest.mark.asyncio
async def test_run_logs_the_package_version_at_startup(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    # run() logs the p2pwatch version (from installed metadata) at startup: the operability
    # signal a correlated-to-version regression relies on (spec 2026-07-10-git-driven-versioning).
    app_holder: dict[str, CrawlerApp] = {}

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        return _ShutdownOnStatusClient(app_holder)

    app = _make_app(tmp_path, matcher_config, factory=factory)
    app_holder["app"] = app
    with caplog.at_level(logging.INFO, logger="p2pwatch.composition.app"):
        await asyncio.wait_for(app.run(), timeout=5.0)
    assert any(r.getMessage() == f"p2pwatch version {version('p2pwatch')}" for r in caplog.records)


# the status loop read the client → the loops did start


@pytest.mark.asyncio
async def test_node_id_override_is_used(tmp_path: Path, matcher_config: MatcherConfig) -> None:
    observation = FileObservation(
        file=FileKey(Network.ED2K, "31d6cfe0d16ae931b73c59d7e0c089c0"),
        filename=_DL_NAME,
        size_bytes=234_000_000,
        source_count=3,
        keyword="keroro",
    )
    app_holder: dict[str, CrawlerApp] = {}

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        return _ShutdownOnStatusClient(app_holder, results=[(observation,)])

    app = _make_app(tmp_path, matcher_config, factory=factory, node_id="forced-node")
    app_holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    catalog = sqlite3.connect(tmp_path / "catalog.db")
    try:
        node_ids = observation_node_ids(catalog)
    finally:
        catalog.close()
    assert node_ids == {"forced-node"}


class _BlockingClient(FakeMuleClient):
    """Client whose ``search`` BLOCKS: the loop stays in flight → cancellation hits it."""

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        await asyncio.Event().wait()  # never resolves: blocks until cancellation
        return SearchAnswer((), 0)


@pytest.mark.asyncio
async def test_a_requested_shutdown_cancels_an_in_flight_search(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # A task is BLOCKED in search; a requested shutdown cancels the loops →
    # covers the cancellation path (clean unwind + "Workers stopped" line).
    app = _make_app(
        tmp_path, matcher_config, factory=lambda endpoint, monotonic_clock: _BlockingClient()
    )
    run_task = asyncio.create_task(app.run())
    for _ in range(20):  # let the tasks start and block in search
        await asyncio.sleep(0)
    app._shutdown.set()
    await asyncio.wait_for(run_task, timeout=5.0)


class _RealPacedClient(FakeMuleClient):
    """Client that paces each status reading with a SMALL REAL sleep (not the FakeTime).

    Used to prove the timing invariant: ``status`` yields REAL time instead of
    busy-spinning, so the status loop advances at a controlled real pace. The normal run
    (without a signal) must OUTLIVE ``shutdown_deadline_seconds`` of real time without raising
    ``TimeoutError`` - the shutdown bound must NOT arm until a shutdown is requested."""

    async def status(self) -> ClientStatus:
        await asyncio.sleep(0.01)  # REAL time: the loop does not occupy the event loop 100%
        return await super().status()


@pytest.mark.asyncio
async def test_normal_run_outlives_shutdown_deadline_without_a_signal(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # Regression (spec §6, DECISION 6): the shutdown bound covers ONLY the shutdown phase. A
    # normal run WITHOUT a signal must run indefinitely - so it must outlive FAR beyond
    # ``shutdown_deadline_seconds`` of REAL time. Before the fix, ``asyncio.timeout`` wrapped
    # all of the supervision (including the UNBOUNDED wait on the signal) on the REAL clock → the
    # run raised ``TimeoutError`` ~deadline after startup, with no shutdown requested. Here the
    # deadline is tiny (0.2 s) and we let 0.4 s of real time pass: the run must
    # STILL be running, without having raised. Then we request the shutdown → it ends CLEANLY.
    app = _make_app(
        tmp_path,
        matcher_config,
        factory=lambda endpoint, monotonic_clock: _RealPacedClient(),
        shutdown_deadline=0.2,
    )
    run_task = asyncio.create_task(app.run())
    await asyncio.sleep(0.4)  # REAL time > deadline: if the bound wrapped the run, it would raise
    assert not run_task.done(), "the normal run (no signal) must NOT finish or raise"
    app._shutdown.set()  # shutdown requested → the bound arms, the clean shutdown is bounded
    await asyncio.wait_for(run_task, timeout=5.0)  # ends without TimeoutError
    assert run_task.exception() is None


def test_the_default_client_factories_pace_on_the_composition_monotonic_clock() -> None:
    endpoint = AmuleEndpoint(client_name="amule-1", host="gluetun", port=4712, password="secret")
    monotonic_clock = FakeTime().monotonic
    for factory in (default_mule_client_factory, default_download_client_factory):
        client = factory(endpoint, monotonic_clock)
        assert isinstance(client, AmuleApiClient)
        assert client._monotonic_clock is monotonic_clock


# A close that drags FAR beyond the armed bound (0.05 s) and FAR beyond the assertion
# threshold (3 s), yet stays BELOW the external guard (30 s). Only the INTERNAL bound
# (armed by ``reschedule``) can cut a close this slow fast enough to land under the
# threshold. If ``reschedule`` regressed, ``aclose`` would block ~10 s then EXIT cleanly
# (no TimeoutError, since the slow close stays below the external guard) and
# ``pytest.raises`` would fail: the test is fail-closed, never "passing" via the guard.
# The 10 s / 3 s separation gives the assertion generous headroom over CI startup jitter
# (``elapsed`` spans the WHOLE run, app setup included), which is why the tighter original
# bounds (1 s / 0.5 s) were flaky under load.
_SLOW_CLOSE_SECONDS = 10.0


class _SlowCloseClient(_ShutdownOnStatusClient):
    """Client whose ``close`` drags beyond the armed bound → the INTERNAL bound cuts it."""

    async def close(self) -> None:
        await asyncio.sleep(_SLOW_CLOSE_SECONDS)  # > armed bound (0.05 s), < external guard (30 s)


@pytest.mark.asyncio
async def test_shutdown_deadline_forces_exit(tmp_path: Path, matcher_config: MatcherConfig) -> None:
    # Close that drags + tiny shutdown deadline → the INTERNAL bound (armed by
    # ``reschedule`` at shutdown) raises TimeoutError (spec §6: the app must NOT appear stuck).
    # ROBUSTNESS: we measure the real elapsed time and require the raise to come FAST (well
    # below the slow close and the external guard) to prove it is the ARMED bound (~0.05 s)
    # that fired, not the external ``wait_for`` (30 s) nor the close end (10 s).
    # A ``reschedule`` regression (bound never armed) would let ``aclose`` exit cleanly
    # after ~10 s WITHOUT TimeoutError → ``pytest.raises`` would fail (fail-closed).
    # ``elapsed`` spans the WHOLE run (app setup included), so the threshold sits at 3 s: far
    # above any plausible CI startup jitter, far below the 10 s slow close.
    app_holder: dict[str, CrawlerApp] = {}

    def factory(endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock) -> _SlowCloseClient:
        return _SlowCloseClient(app_holder)

    app = _make_app(tmp_path, matcher_config, factory=factory, shutdown_deadline=0.05)
    app_holder["app"] = app
    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(app.run(), timeout=30.0)
    elapsed = loop.time() - started
    # < 3 s: well below the slow close (10 s) and the external guard (30 s) → it is indeed the
    # armed bound (~0.05 s) that cut the close, not some other delay.
    assert elapsed < 3.0, f"the armed bound must cut fast, elapsed={elapsed:.3f}s"


@pytest.mark.asyncio
async def test_observations_are_catalogued(tmp_path: Path, matcher_config: MatcherConfig) -> None:
    observation = FileObservation(
        file=FileKey(Network.ED2K, "31d6cfe0d16ae931b73c59d7e0c089c0"),
        filename=_DL_NAME,
        size_bytes=234_000_000,
        source_count=3,
        keyword="keroro",
    )
    app_holder: dict[str, CrawlerApp] = {}

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        return _ShutdownOnStatusClient(app_holder, results=[(observation,)])

    app = _make_app(tmp_path, matcher_config, factory=factory)
    app_holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    catalog = sqlite3.connect(tmp_path / "catalog.db")
    try:
        count = catalog.execute("SELECT count(*) FROM match_decisions").fetchone()[0]
    finally:
        catalog.close()
    assert count == 1


class _KadNeverEndsClient(FakeMuleClient):
    """Its ``kad`` searches never return; the third ``ed2k`` search of ``keroro`` shuts down."""

    def __init__(self, app_holder: dict[str, CrawlerApp]) -> None:
        super().__init__()
        self._app_holder = app_holder

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        if channel == "kad":
            await asyncio.Event().wait()
        answer = await super().search(keyword, channel, budget_seconds)
        app = self._app_holder["app"]
        if self.searches.count(("keroro", "ed2k")) == 3 and not app._shutdown.is_set():
            app._shutdown.set()
        return answer


@pytest.mark.asyncio
async def test_a_channel_that_never_ends_does_not_hold_the_other_back(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    app_holder: dict[str, CrawlerApp] = {}
    client = _KadNeverEndsClient(app_holder)
    app = _make_app(tmp_path, matcher_config, factory=lambda endpoint, monotonic_clock: client)
    app_holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    assert ("titar", "ed2k") in client.searches


# ed2k's `keroro` runs past 60 s, so both ed2k rules take turns binding (spec stage 2, section 4).
_DURATIONS = {"keroro": 90.0, "keroro mission": 30.0, "titar": 30.0}
_KAD_TARGETS = {"keroro": "keroro", "keroro mission": "keroro", "titar": "titar"}
_HOUR = 3600.0


def _starts(api: FakeAmuleApi, search_type: str) -> list[tuple[float, str]]:
    """Every ``POST /search`` of one type: seconds since the start, and its query."""
    bodies = [
        ((moment - MONOTONIC_EPOCH).total_seconds(), json.loads(request.content))
        for moment, request in api.calls
        if request.method == "POST" and request.url.path == "/api/v1/search"
    ]
    return [(moment, body["query"]) for moment, body in bodies if body["type"] == search_type]


def test_an_hour_of_the_running_app_keeps_to_the_networks_rules(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    monotonic_clock = LoopMonotonicClock()
    api = FakeAmuleApi(monotonic_clock=monotonic_clock, search_seconds=dict(_DURATIONS))

    async def main() -> None:
        app = CrawlerApp(
            crawler_config=_crawler_config(tmp_path, keywords=tuple(_DURATIONS)),
            targets=_TARGETS,
            matcher_config=matcher_config,
            wall_clock=LoopWallClock(),
            monotonic_clock=monotonic_clock,
            rng=_NoopRng(),
            wake_hub=RecordingWakeHub(),
            policy_fingerprint=_FP,
            webui_address=_WEBUI_ADDRESS,
            amule_api_address=_AMULE_API_ADDRESS,
            client_factory=lambda endpoint, monotonic_clock: AmuleApiClient(
                endpoint.host,
                endpoint.port,
                PASSWORD,
                transport=api.transport(),
                monotonic_clock=monotonic_clock,
            ),
        )
        asyncio.get_running_loop().call_later(_HOUR, app._shutdown.set)
        await app.run()

    run_virtual(main())

    ed2k = _starts(api, "global")
    assert len(ed2k) > 30
    for (previous, query), (start, _) in zip(ed2k, ed2k[1:], strict=False):
        assert start >= previous + max(60.0, _DURATIONS[query]), (previous, query, start)
    kad = _starts(api, "kad")
    for target in ("keroro", "titar"):
        times = [moment for moment, query in kad if _KAD_TARGETS[query] == target]
        assert len(times) > 30
        gaps = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
        assert min(gaps) >= 60, target


class _StampedSearchClient(FakeMuleClient):
    """Stamps each search on the monotonic clock; the first one fires the shutdown."""

    def __init__(self, app_holder: dict[str, CrawlerApp], monotonic_clock: MonotonicClock) -> None:
        super().__init__()
        self._app_holder = app_holder
        self._monotonic_clock = monotonic_clock
        self.searched_at: list[MonotonicInstant] = []

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        if not self.searched_at:
            self._app_holder["app"]._shutdown.set()
        self.searched_at.append(self._monotonic_clock.now())
        return await super().search(keyword, channel, budget_seconds)


@pytest.mark.asyncio
async def test_a_backoff_the_previous_run_saved_holds_the_first_search(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    fake_time = FakeTime()
    delay = timedelta(hours=1)
    local = open_local(tmp_path / "local.db")
    SqliteBackoffStateRepository(local).save_backoff_states(
        {BackoffKey(AMULE_CLIENT_NAME, None): BackoffState(1, fake_time.wall.now(), delay)}
    )
    local.close()
    holder: dict[str, CrawlerApp] = {}
    client = _StampedSearchClient(holder, fake_time.monotonic)
    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: client,
    )
    holder["app"] = app
    started_at = fake_time.monotonic.now()
    await asyncio.wait_for(app.run(), timeout=5.0)
    assert client.searched_at[0] - started_at >= delay


# ---------------------------------------------------------------------------
# Task 6 - startup re-evaluation wiring (policy-fingerprint gate)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_runs_and_stores_marker_when_policy_never_set(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    # Fresh local.db (never re-evaluated before) -> the gate RUNS the re-evaluation (against an
    # EMPTY catalog.db, since it runs BEFORE the first search records anything) and
    # stores the fingerprint, so a LATER restart with the SAME policy would skip it.
    holder: dict[str, CrawlerApp] = {}

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        return _ShutdownOnStatusClient(holder)

    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint="fp-first-run",
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=factory,
    )
    holder["app"] = app
    with caplog.at_level(logging.INFO, logger="p2pwatch.application.reevaluate_if_policy_changed"):
        await asyncio.wait_for(app.run(), timeout=5.0)
    assert any(
        r.getMessage() == "catalogue re-evaluated: 0 files, 0 rows written" for r in caplog.records
    )
    local_conn = sqlite3.connect(tmp_path / "local.db")
    try:
        stored = local_conn.execute(
            "SELECT policy_fingerprint FROM reevaluation_state WHERE id = 1"
        ).fetchone()
    finally:
        local_conn.close()
    assert stored == ("fp-first-run",)


@pytest.mark.asyncio
async def test_backfill_skipped_when_marker_already_matches_fingerprint(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    # Pre-seed local.db with the SAME fingerprint the app is built with -> the gate SKIPS
    # the pass (a restart with an unchanged matcher.yml/targets.yml does no redundant work).
    local_conn = open_local(tmp_path / "local.db")
    try:
        SqliteLocalStateRepository(local_conn).set_reevaluated_policy_fingerprint("fp-unchanged")
    finally:
        local_conn.close()
    holder: dict[str, CrawlerApp] = {}

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        return _ShutdownOnStatusClient(holder)

    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint="fp-unchanged",
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=factory,
    )
    holder["app"] = app
    with caplog.at_level(logging.INFO, logger="p2pwatch.application.reevaluate_if_policy_changed"):
        await asyncio.wait_for(app.run(), timeout=5.0)
    assert any(
        r.getMessage() == "policy unchanged: catalogue re-evaluation skipped"
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# Full mode (download.enabled): wiring of the download loop
# ---------------------------------------------------------------------------


class FakeDownloadClient(FakeMuleClient):
    """Test download client: also satisfies start/downloads/sources (no-op).

    ``queue_calls`` counts the list polls: proof that a download-loop cycle DID
    run (``downloads`` is the only network ``await`` of an empty cycle)."""

    def __init__(self) -> None:
        super().__init__()
        self.queue_calls = 0

    async def start(self, request: DownloadRequest) -> None:
        return None

    async def downloads(self) -> tuple[DownloadStatus, ...]:
        self.queue_calls += 1
        return ()

    async def sources(self, file: FileKey) -> tuple[SourceReading, ...]:
        return ()


class _ShutdownOnQueueDownloadClient(FakeDownloadClient):
    """Download client that fires the shutdown on the FIRST ``downloads`` (1 cycle, stop).

    Bounds the run DETERMINISTICALLY on the DOWNLOAD loop itself: the shutdown is set
    ONLY once the download loop has run a cycle (queue poll) → proves that the
    loop body ran (not just that the task was created), without a timing race
    nor a real ``sleep``. The ``queue_calls`` counter stays readable afterwards."""

    def __init__(self, app_holder: dict[str, CrawlerApp]) -> None:
        super().__init__()
        self._app_holder = app_holder

    async def downloads(self) -> tuple[DownloadStatus, ...]:
        result = await super().downloads()
        self._app_holder["app"]._shutdown.set()  # shutdown AFTER the 1st download cycle
        return result


@pytest.mark.asyncio
async def test_observer_mode_runs_without_the_download_loop(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # download absent → observer: starts, searches, stops; no download client built.
    holder: dict[str, CrawlerApp] = {}
    built: list[AmuleEndpoint] = []

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        return _ShutdownOnStatusClient(holder)

    def download_factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> FakeDownloadClient:
        built.append(endpoint)
        return FakeDownloadClient()

    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path),  # no download → observer
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=factory,
        download_client_factory=download_factory,
    )
    holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    assert built == []  # observer: no download connection is ever opened


@pytest.mark.asyncio
async def test_full_mode_runs_the_download_loop(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    # The shutdown is driven DETERMINISTICALLY by the DOWNLOAD loop itself (the download
    # client fires the shutdown on its 1st queue poll) → we prove that the BODY of the download
    # loop ran (not just that the task was created), without a timing race.
    holder: dict[str, CrawlerApp] = {}
    download_client = _ShutdownOnQueueDownloadClient(holder)

    def search_factory(endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock) -> FakeMuleClient:
        return FakeMuleClient()  # does NOT drive the shutdown: the download loop arms it

    app = CrawlerApp(
        crawler_config=_full_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=search_factory,
        download_client_factory=lambda endpoint, monotonic_clock: download_client,
    )
    holder["app"] = app
    with caplog.at_level(logging.INFO, logger="p2pwatch.composition.app"):
        await asyncio.wait_for(app.run(), timeout=5.0)
    # the download loop ran ≥ 1 cycle (body ran, not just the task created).
    assert download_client.queue_calls >= 1
    assert "download enabled: download loop armed" in caplog.messages


class _ShutdownOnSourcesDownloadClient(FakeDownloadClient):
    """Lists one download and one source of it, firing the shutdown on that read."""

    def __init__(self, app_holder: dict[str, CrawlerApp], file: FileKey) -> None:
        super().__init__()
        self._app_holder = app_holder
        self._file = file

    async def downloads(self) -> tuple[DownloadStatus, ...]:
        return (DownloadStatus(self._file, 0, 100, False, None, None),)

    async def sources(self, file: FileKey) -> tuple[SourceReading, ...]:
        self._app_holder["app"]._shutdown.set()
        source = SourceKey(Network.ED2K, "1f" * 16)
        return (SourceReading(source, "peer", None, SourceRole.QUEUED, None, None, (), 0),)


@pytest.mark.asyncio
async def test_full_mode_records_the_sources_of_a_download_in_the_catalog(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    file = FileKey(Network.ED2K, "a" * 32)
    local = open_local(tmp_path / "local.db")
    SqliteDownloadRepository(local).record_queued(file, "062A", 100, FakeTime().wall.now())
    local.close()
    catalog = open_catalog(tmp_path / "catalog.db")
    insert_file(catalog, file.native_id)
    catalog.close()
    holder: dict[str, CrawlerApp] = {}
    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path, node_id="n1", download=_download_config(tmp_path)),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: FakeMuleClient(),
        download_client_factory=lambda endpoint, monotonic_clock: _ShutdownOnSourcesDownloadClient(
            holder, file
        ),
    )
    holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    catalog = open_catalog(tmp_path / "catalog.db")
    rows = catalog.execute(
        "SELECT v.name, v.node_id FROM source_observations AS o JOIN source_variants AS v"
        " USING (variant_id)"
    ).fetchall()
    catalog.close()
    assert rows == [("peer", "n1")]


@pytest.mark.asyncio
async def test_the_rows_written_carry_the_apps_wall_clock(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # A year the wall clock cannot be in, so a row stamped on any other clock fails the bounds.
    wall_clock = FakeTime(datetime(2030, 1, 1, tzinfo=UTC)).wall
    seeded_at = datetime(2029, 12, 31, 23, tzinfo=UTC)
    file = FileKey(Network.ED2K, "a" * 32)
    catalog = open_catalog(tmp_path / "catalog.db")
    SqliteCatalogRepository(catalog, "n1").record_observation(
        FileObservation(file=file, filename=_DL_NAME, size_bytes=100, source_count=1, keyword="k"),
        seeded_at,
    )
    catalog.close()
    local = open_local(tmp_path / "local.db")
    SqliteDownloadRepository(local).record_queued(file, "062A", 100, seeded_at)
    local.close()
    holder: dict[str, CrawlerApp] = {}
    app = CrawlerApp(
        crawler_config=_full_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=wall_clock,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: FakeMuleClient(),
        download_client_factory=lambda endpoint, monotonic_clock: _ShutdownOnSourcesDownloadClient(
            holder, file
        ),
    )
    start = utc_iso(wall_clock.now())
    holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    catalog = open_catalog(tmp_path / "catalog.db")
    local = open_local(tmp_path / "local.db")
    stamps = {
        "decided_at": catalog.execute("SELECT decided_at FROM match_decisions").fetchone()[0],
        "created_at": local.execute(
            "SELECT value FROM node_runtime WHERE key = 'created_at'"
        ).fetchone()[0],
        "last_seen_at": local.execute("SELECT last_seen_at FROM downloads").fetchone()[0],
    }
    catalog.close()
    local.close()
    end = utc_iso(wall_clock.now())
    assert all(start <= stamp <= end for stamp in stamps.values()), (start, stamps, end)


@pytest.mark.asyncio
async def test_full_mode_reads_sources_at_their_interval_and_spaces_them_by_a_poll_more(
    tmp_path: Path, matcher_config: MatcherConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Source points spec, D3: the writer's tolerance follows the spacing, interval plus a poll.
    holder: dict[str, CrawlerApp] = {}
    spacings: list[timedelta] = []
    loops: list[DownloadLoopDeps] = []

    def source_repository(
        connection: sqlite3.Connection, node_id: str, time_between_reads: timedelta
    ) -> SqliteSourceRepository:
        spacings.append(time_between_reads)
        return SqliteSourceRepository(connection, node_id, time_between_reads)

    async def loop(deps: DownloadLoopDeps) -> None:
        loops.append(deps)
        holder["app"]._shutdown.set()

    monkeypatch.setattr(composition_app, "SqliteSourceRepository", source_repository)
    monkeypatch.setattr(composition_app, "download_loop", loop)
    download = replace(_download_config(tmp_path), sources_interval=timedelta(seconds=120))
    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path, download=download),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: FakeMuleClient(),
        download_client_factory=lambda endpoint, monotonic_clock: FakeDownloadClient(),
    )
    holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    assert spacings == [timedelta(seconds=150)]
    assert [deps.sources_interval for deps in loops] == [timedelta(seconds=120)]


# does not raise: connect tolerated


class _BlockingPollMonotonicClock(FakeMonotonicClock):
    """Monotonic clock whose LONG sleeps (≥ 5 s) BLOCK for good (on an Event that is never set).

    Models the IN-CYCLE sleep of the download loop (``_sleep_or_wake``, 30 s poll): it stays
    BLOCKED in its ``sleep``, so the loop CANNOT re-test ``self._shutdown`` on its own; only
    an explicit CANCELLATION by ``supervise_loops`` gets it out. A BARRIER: as soon as the download
    poll has entered a long sleep, we ARM ``self._shutdown`` - the shutdown is thus requested
    while it is blocked. If ``supervise_loops`` did NOT cancel it, the ``TaskGroup`` would wait
    forever and the armed ``shutdown_deadline`` would fire a ``TimeoutError`` (force-exit): the
    test would
    fail fail-closed. The SHORT sleeps yield immediately (determinism, no real time)."""

    def __init__(self, app_holder: dict[str, CrawlerApp]) -> None:
        super().__init__(FakeTime())
        self._app_holder = app_holder
        self._blocked_long_polls: set[timedelta] = set()
        self._never = asyncio.Event()

    async def sleep(self, duration: timedelta) -> None:
        if duration < timedelta(seconds=5):
            await super().sleep(duration)  # short pause: yields (instantaneous)
            return
        # Long sleep (in-cycle poll of a loop): we note the pace and,
        # as soon as the download poll (30 s) is blocked, we request the shutdown WHILE it
        # sleeps, then we BLOCK for good.
        self._blocked_long_polls.add(duration)
        if timedelta(seconds=30) in self._blocked_long_polls:
            self._app_holder["app"]._shutdown.set()
        await self._never.wait()  # NEVER resolves: exit only via cancellation


@pytest.mark.asyncio
async def test_full_mode_shutdown_cancels_the_download_loop_promptly(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # REGRESSION (holistic review): at shutdown, ``supervise_loops`` must EXPLICITLY cancel the
    # download loop (sibling task of the search ``loop_task``). Without this, it stays
    # blocked in its in-cycle sleep (``_sleep_or_wake`` does NOT watch ``self._shutdown``),
    # the ``TaskGroup`` waits on its poll (30 s), the ``shutdown_deadline`` fires a
    # ``TimeoutError`` FIRST and the shutdown is FORCED - not clean. Here: a clock whose long
    # sleeps BLOCK, which ARMS the shutdown once the loop is blocked in its poll. If the
    # cancellation happens, ``run()`` RETURNS promptly (without reaching the deadline); otherwise
    # it would ``TimeoutError`` (deadline) or block until the external guard → fail-closed failure.
    holder: dict[str, CrawlerApp] = {}
    monotonic_clock = _BlockingPollMonotonicClock(holder)

    # _full_crawler_config: download poll 30 s, shutdown_deadline 30 s.
    app = CrawlerApp(
        crawler_config=_full_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=monotonic_clock,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: FakeMuleClient(),
        download_client_factory=lambda endpoint, monotonic_clock: FakeDownloadClient(),
    )
    holder["app"] = app
    # The external guard (3 s of REAL time) is WELL below the shutdown_deadline (30 s) AND below
    # the polls (10 s/30 s): it can only fire if the shutdown is NOT prompt. With the
    # cancellation, the run returns within a few event-loop ticks (no real time is consumed).
    await asyncio.wait_for(app.run(), timeout=3.0)


@pytest.mark.asyncio
async def test_full_mode_shutdown_leaves_no_task_leaked(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # T12 - shutdown INVARIANT "no task leak". The ``TaskGroup`` guarantees BY
    # CONSTRUCTION that on exit from ``run()`` neither loop (search/download) survives: its
    # ``__aexit__`` waits for ALL its tasks to finish, and ``supervise_loops``
    # cancels them ALL explicitly at shutdown. This test LOCKS the invariant: it would fail if
    # a future regression detached a loop from the ``TaskGroup`` (``asyncio.create_task`` outside
    # the group) or forgot to cancel a sibling task - a ``pending`` task would then survive
    # ``run()``. We prove it by DIFFERENCE: the tasks born DURING ``run()`` (full = both
    # loops blocked in their sleep, shutdown armed once blocked) must ALL be
    # finished once ``run()`` has returned. The ``_BlockingPollMonotonicClock`` forces the worst
    # case: the loops can only exit VIA the explicit cancellation by ``supervise_loops``.
    holder: dict[str, CrawlerApp] = {}
    monotonic_clock = _BlockingPollMonotonicClock(holder)
    app = CrawlerApp(
        crawler_config=_full_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=monotonic_clock,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: FakeMuleClient(),
        download_client_factory=lambda endpoint, monotonic_clock: FakeDownloadClient(),
    )
    holder["app"] = app
    before = asyncio.all_tasks()  # snapshot BEFORE (the test task + pytest-asyncio infra)
    await asyncio.wait_for(app.run(), timeout=3.0)
    # Tasks born DURING the run (the loops of the TaskGroup): all must be finished.
    # No ``pending`` task must remain - otherwise a loop leaked the lifecycle.
    leaked = [task for task in asyncio.all_tasks() - before if not task.done()]
    assert leaked == [], f"leaked tasks after shutdown: {leaked!r}"


# ---------------------------------------------------------------------------
# Task 8 - metrics + CrawlerStarted + log_level bootstrap
# ---------------------------------------------------------------------------


# server started because metrics.enabled=True


# metrics.enabled=False → no server


# obs=None → no server


@pytest.mark.asyncio
async def test_emits_crawler_started_observer_mode(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """CrawlerStarted(download_enabled=False) emitted at boot, download off."""
    holder: dict[str, CrawlerApp] = {}

    def factory(
        endpoint: AmuleEndpoint, monotonic_clock: MonotonicClock
    ) -> _ShutdownOnStatusClient:
        return _ShutdownOnStatusClient(holder)

    app = _make_app(tmp_path, matcher_config, factory=factory)
    holder["app"] = app
    with caplog.at_level(logging.INFO, logger="p2pwatch.observability"):
        await asyncio.wait_for(app.run(), timeout=5.0)
    assert any("download off" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_emits_crawler_started_full_mode(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """CrawlerStarted(download_enabled=True) emitted at boot, download on."""
    holder: dict[str, CrawlerApp] = {}
    download_client = _ShutdownOnQueueDownloadClient(holder)

    app = CrawlerApp(
        crawler_config=_full_crawler_config(tmp_path),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: FakeMuleClient(),
        download_client_factory=lambda endpoint, monotonic_clock: download_client,
    )
    holder["app"] = app
    with caplog.at_level(logging.INFO, logger="p2pwatch.observability"):
        await asyncio.wait_for(app.run(), timeout=5.0)
    assert any("download on" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# WebUI in-process (spec §5): own thread + loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_webui_reads_the_status_loops_board_and_the_pause_gate(
    tmp_path: Path, matcher_config: MatcherConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder: dict[str, CrawlerApp] = {}
    wired: dict[str, Any] = {}

    def build(**kwargs: Any) -> Starlette:
        wired.update(kwargs)
        return Starlette()

    monkeypatch.setattr(composition_app, "build_webui_app", build)
    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path, webui=WebuiConfig(enabled=True)),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: _ShutdownOnStatusClient(holder),
    )
    holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    reading = wired["status_readings"].readings()["amuled"]
    assert reading.status == await FakeMuleClient().status()
    assert wired["status_readings"].is_current("amuled")
    assert wired["control"].is_paused() is False


@pytest.mark.asyncio
async def test_the_webui_cuts_periods_at_its_configured_gap_and_reads_the_crawlers_clocks(
    tmp_path: Path, matcher_config: MatcherConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A reading option, so a crawl-only node has one too (source points spec, D6).
    holder: dict[str, CrawlerApp] = {}
    wired: dict[str, Any] = {}

    def build(**kwargs: Any) -> Starlette:
        wired.update(kwargs)
        return Starlette()

    monkeypatch.setattr(composition_app, "build_webui_app", build)
    fake_time = FakeTime()
    webui = WebuiConfig(enabled=True, source_period_gap=timedelta(seconds=600))
    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path, webui=webui),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: _ShutdownOnStatusClient(holder),
    )
    holder["app"] = app
    await asyncio.wait_for(app.run(), timeout=5.0)
    assert wired["source_period_gap"] == timedelta(seconds=600)
    assert wired["wall_clock"] is fake_time.wall
    assert wired["monotonic_clock"] is fake_time.monotonic


@pytest.mark.asyncio
async def test_webui_not_started_when_disabled(
    tmp_path: Path, matcher_config: MatcherConfig, caplog: pytest.LogCaptureFixture
) -> None:
    holder: dict[str, CrawlerApp] = {}
    app = CrawlerApp(
        crawler_config=_crawler_config(tmp_path, webui=WebuiConfig(enabled=False)),
        targets=_TARGETS,
        matcher_config=matcher_config,
        wall_clock=FakeTime().wall,
        monotonic_clock=FakeTime().monotonic,
        rng=_NoopRng(),
        wake_hub=RecordingWakeHub(),
        policy_fingerprint=_FP,
        webui_address=_WEBUI_ADDRESS,
        amule_api_address=_AMULE_API_ADDRESS,
        client_factory=lambda endpoint, monotonic_clock: _ShutdownOnStatusClient(holder),
    )
    holder["app"] = app
    with caplog.at_level(logging.INFO, logger=_WEBUI_LOGGER):
        await asyncio.wait_for(app.run(), timeout=5.0)
    assert not any(record.name == _WEBUI_LOGGER for record in caplog.records)


# ---------------------------------------------------------------------------
# Runtime controls (phase P6a): the pause gate, restart-through-control.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_starts_unpaused(tmp_path: Path, matcher_config: MatcherConfig) -> None:
    app = _make_app(
        tmp_path, matcher_config, factory=lambda endpoint, monotonic_clock: FakeMuleClient()
    )
    assert app._resumed.is_set()


@pytest.mark.asyncio
async def test_resumed_gate_blocks_when_cleared_and_releases_when_set(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # Focused gate semantics: cleared ``_resumed`` blocks a waiter; setting it releases it.
    app = _make_app(
        tmp_path, matcher_config, factory=lambda endpoint, monotonic_clock: FakeMuleClient()
    )
    app._resumed.clear()  # paused
    gate = asyncio.create_task(app._resumed.wait())
    await asyncio.sleep(0)
    assert not gate.done()
    app._resumed.set()  # resume
    await asyncio.wait_for(gate, timeout=1.0)
    assert gate.done()


class _ShutdownOnSearchClient(FakeMuleClient):
    """Fires the shutdown on the first search."""

    def __init__(self, app_holder: dict[str, CrawlerApp]) -> None:
        super().__init__()
        self._app_holder = app_holder

    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        if not self.searches:
            self._app_holder["app"]._shutdown.set()
        return await super().search(keyword, channel, budget_seconds)


@pytest.mark.asyncio
async def test_pause_gate_blocks_the_searches_until_resumed(
    tmp_path: Path, matcher_config: MatcherConfig
) -> None:
    # WIRING: a paused app (``_resumed`` cleared before run) blocks at the tasks' gate BEFORE any
    # search - the client is never searched and the run cannot self-shutdown. Resuming releases
    # the gate → a search runs, fires the shutdown, exits. Without the gate, the tasks would
    # search immediately and the run would finish before resume.
    holder: dict[str, CrawlerApp] = {}
    client = _ShutdownOnSearchClient(holder)
    app = _make_app(tmp_path, matcher_config, factory=lambda endpoint, monotonic_clock: client)
    holder["app"] = app
    app._resumed.clear()  # start paused
    run_task = asyncio.create_task(app.run())
    for _ in range(100):  # ample ticks for ungated tasks to have searched + shut down
        await asyncio.sleep(0)
    assert client.searches == []  # paused: no search ran
    assert not run_task.done()  # blocked at the gate, no self-shutdown
    app._resumed.set()  # resume → the tasks search
    await asyncio.wait_for(run_task, timeout=5.0)
    assert client.searches  # a search ran after resume
