import dataclasses
import sqlite3
from datetime import timedelta

import pytest

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.persistence_sqlite.catalog_repository import SqliteCatalogRepository
from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.variants import iso_to_micros
from p2pwatch.application.search_worker import (
    SEARCH_BUDGET_SECONDS,
    BackoffPolicy,
    BackoffRegistry,
    SearchTask,
    SearchWorker,
    WorkerDeps,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability.events import (
    ClientUnreachable,
    ObservationRecorded,
    SearchExecuted,
    SearchFailed,
)
from p2pwatch.domain.observation import FileObservation
from p2pwatch.ports.driven.backoff_state_repository import BackoffKey, BackoffState
from p2pwatch_testing.application.fakes import (
    FakeLogger,
    FakeRng,
    FakeSearchClient,
    FakeTime,
    LoggedLine,
    RecordingTelemetry,
    RecordingWakeHub,
    make_search_failed,
    make_unreachable,
)
from p2pwatch_testing.catalog_rows import count_observations

_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
_CLIENT = BackoffKey("amule-1", None)
_KAD = BackoffKey("amule-1", "kad")
_ED2K = BackoffKey("amule-1", "ed2k")

# jitter_ratio 0.0 + FakeRng(jitter_value=0.0) → backoff = exact NOMINAL delay (clean assertions).
_POLICY = BackoffPolicy(
    base_seconds=2.0,
    cap_seconds=60.0,
    factor=2.0,
    jitter_ratio=0.0,
)


def _obs() -> FileObservation:
    return FileObservation(
        file=FileKey(Network.ED2K, _HASH),
        filename=_DL_NAME,
        size_bytes=234_000_000,
        source_count=3,
        keyword="keroro",
    )


def _registry(fake_time: FakeTime, rng: FakeRng | None = None) -> BackoffRegistry:
    return BackoffRegistry(_POLICY, fake_time.wall, fake_time.monotonic, rng or FakeRng())


def _deps(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    backoff: BackoffRegistry,
    fake_time: FakeTime,
    *,
    telemetry: RecordingTelemetry | None = None,
    logger: FakeLogger | None = None,
    observation_logger: FakeLogger | None = None,
) -> WorkerDeps:
    return WorkerDeps(
        catalog=catalog,
        engine=engine,
        wake_hub=RecordingWakeHub(),
        backoff=backoff,
        telemetry=telemetry or RecordingTelemetry(),
        wall_clock=fake_time.wall,
        logger=logger or FakeLogger(),
        observation_logger=observation_logger or FakeLogger(),
    )


# --- BackoffRegistry (logic, deterministic via fake time/rng) ---


def test_backoff_registry_grows_then_resets() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    assert registry.record_failure(_KAD) == timedelta(seconds=2)  # 1st attempt = base
    fake_time.advance(timedelta(seconds=2.0))
    assert registry.record_failure(_KAD) == timedelta(seconds=4)  # × factor
    registry.reset(_KAD)
    assert registry.record_failure(_KAD) == timedelta(seconds=2)  # back to base


def test_a_failure_while_backed_off_does_not_count_again() -> None:
    # Concurrent searches started before a backoff fail together: one round, one attempt.
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.advance(timedelta(seconds=0.5))
    # what is left of the backoff already set
    assert registry.record_failure(_KAD) == timedelta(seconds=1.5)
    fake_time.advance(timedelta(seconds=1.5))
    assert registry.record_failure(_KAD) == timedelta(seconds=4)  # the second attempt


def test_backoff_registry_keys_are_independent() -> None:
    registry = _registry(FakeTime())
    assert registry.record_failure(_KAD) == timedelta(seconds=2)
    assert registry.record_failure(_ED2K) == timedelta(seconds=2)  # not kad's counter


def test_backoff_registry_reset_unknown_key_is_a_noop() -> None:
    _registry(FakeTime()).reset(_KAD)  # does not raise


def test_a_failure_backs_its_key_off_for_its_delay() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=1.9))  # still before its delay (2.0s)
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=0.1))
    assert registry.is_in_backoff(_KAD) is False


def test_a_wall_clock_step_forward_keeps_the_key_backed_off() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.step_wall(timedelta(hours=1))
    assert registry.is_in_backoff(_KAD) is True


def test_a_wall_clock_step_back_releases_the_key_at_its_delay() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.step_wall(timedelta(hours=-1))
    fake_time.advance(timedelta(seconds=1.9))
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=0.1))
    assert registry.is_in_backoff(_KAD) is False


def test_backoff_registry_unknown_key_is_not_in_backoff() -> None:
    assert _registry(FakeTime()).is_in_backoff(_KAD) is False


def test_backoff_registry_jitter_extends_the_delay() -> None:
    fake_time = FakeTime()
    policy = dataclasses.replace(_POLICY, jitter_ratio=0.5)  # jitter in [0, 0.5*delay)
    rng = FakeRng(jitter_value=1.0)  # constant 1.0s jitter
    registry = BackoffRegistry(policy, fake_time.wall, fake_time.monotonic, rng)
    delay = registry.record_failure(_KAD)
    assert delay == timedelta(seconds=3)  # base 2.0 + jitter 1.0
    assert rng.jitter_spans == [1.0]  # span = jitter_ratio (0.5) * delay (2.0)


def test_the_snapshot_holds_each_waits_start_on_the_wall_clock_and_its_delay() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    started_at = fake_time.wall.now()
    fake_time.advance(timedelta(seconds=1))
    assert registry.snapshot() == {_KAD: BackoffState(1, started_at, timedelta(seconds=2))}


def test_a_loaded_backoff_waits_what_is_left_of_its_delay() -> None:
    fake_time = FakeTime()
    started_at = fake_time.wall.now() - timedelta(seconds=100)
    registry = _registry(fake_time)
    registry.load_from({_KAD: BackoffState(1, started_at, timedelta(seconds=300))})
    assert registry.time_until_retry(_KAD) == timedelta(seconds=200)


def test_a_loaded_backoff_started_in_the_future_waits_its_delay_at_most() -> None:
    fake_time = FakeTime()
    started_at = fake_time.wall.now() + timedelta(hours=1)
    registry = _registry(fake_time)
    registry.load_from({_KAD: BackoffState(1, started_at, timedelta(seconds=300))})
    fake_time.advance(timedelta(seconds=299))
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=1))
    assert registry.is_in_backoff(_KAD) is False


def test_a_loaded_backoff_keeps_its_attempts() -> None:
    fake_time = FakeTime()
    started_at = fake_time.wall.now() - timedelta(hours=1)
    registry = _registry(fake_time)
    registry.load_from({_KAD: BackoffState(2, started_at, timedelta(seconds=4))})
    assert registry.is_in_backoff(_KAD) is False
    assert registry.record_failure(_KAD) == timedelta(seconds=8)  # the third attempt


def test_a_worker_declares_the_channels_of_its_client(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    client = FakeSearchClient()
    client.channels = ("kad",)
    worker = SearchWorker(
        "amule-1", client, _deps(catalog, engine, _registry(fake_time), fake_time)
    )
    assert worker.channels == ("kad",)


@pytest.mark.parametrize(
    ("failed", "ready_in_seconds"),
    [((), 0), ((_CLIENT,), 2), ((_KAD,), 2), ((_ED2K,), 0)],
)
def test_a_worker_is_ready_for_a_channel_when_neither_it_nor_the_channel_is_backed_off(
    catalog: SqliteCatalogRepository,
    engine: MatchingEngine,
    failed: tuple[BackoffKey, ...],
    ready_in_seconds: int,
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    for key in failed:
        registry.record_failure(key)
    worker = SearchWorker(
        "amule-1", FakeSearchClient(), _deps(catalog, engine, registry, fake_time)
    )
    assert worker.time_until_ready("kad") == timedelta(seconds=ready_in_seconds)
    fake_time.advance(timedelta(seconds=3.0))
    assert worker.time_until_ready("kad") == timedelta(0)  # a past backoff is no wait


def test_a_worker_waits_for_the_later_of_its_two_backoffs(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.advance(timedelta(seconds=1.0))
    registry.record_failure(_CLIENT)
    worker = SearchWorker(
        "amule-1", FakeSearchClient(), _deps(catalog, engine, registry, fake_time)
    )
    assert worker.time_until_ready("kad") == timedelta(seconds=2)
    fake_time.advance(timedelta(seconds=1.5))
    registry.reset(_CLIENT)
    assert worker.time_until_ready("kad") == timedelta(0)  # the channel's own ended first


# --- SearchWorker ---


@pytest.mark.asyncio
async def test_successful_task_records_observation(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    client = FakeSearchClient(results=[(_obs(),)])
    worker = SearchWorker(
        "amule-1", client, _deps(catalog, engine, _registry(fake_time), fake_time)
    )
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert client.searches == [("keroro", "ed2k")]
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1
    observed_at = catalog_connection.execute("SELECT observed_at FROM observations").fetchone()
    assert observed_at == (iso_to_micros(utc_iso(fake_time.wall.now())),)


@pytest.mark.asyncio
async def test_multiple_observations_some_unchanged_are_all_processed(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    discarded = FileObservation(
        file=FileKey(Network.ED2K, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        filename="random.txt",  # discarded by the engine → record_observation returns False
        size_bytes=10,
        source_count=1,
        keyword="keroro",
    )
    # Two observations in the same readout: the 1st is discarded (False → loop back), the 2nd
    # changes a verdict. Covers the "if False → next observation" edge.
    client = FakeSearchClient(results=[(discarded, _obs())])
    worker = SearchWorker(
        "amule-1", client, _deps(catalog, engine, _registry(fake_time), fake_time)
    )
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert count_observations(catalog_connection) == 2
    assert catalog_connection.execute("SELECT count(*) FROM match_decisions").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_connect_failure_arms_instance_backoff_and_skips_the_item(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    client = FakeSearchClient(connect_failures=[make_unreachable()])
    worker = SearchWorker("amule-1", client, _deps(catalog, engine, registry, fake_time))
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert client.searches == []  # item dropped, never searched
    assert registry.is_in_backoff(_CLIENT) is True  # client in backoff (skip until retry)


@pytest.mark.asyncio
async def test_backoff_expires_and_item_runs_again(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)  # 2.0s
    client = FakeSearchClient(results=[(_obs(),)])
    worker = SearchWorker("amule-1", client, _deps(catalog, engine, registry, fake_time))
    fake_time.advance(timedelta(seconds=3.0))  # the channel is no longer in backoff
    await worker.run_task(SearchTask(keyword="k", channel="kad"))
    assert client.searches == [("k", "kad")]


@pytest.mark.asyncio
async def test_already_connected_does_not_reconnect(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    client = FakeSearchClient(results=[(), ()])
    worker = SearchWorker(
        "amule-1", client, _deps(catalog, engine, _registry(fake_time), fake_time)
    )
    await worker.run_task(SearchTask(keyword="k1", channel="ed2k"))
    await worker.run_task(SearchTask(keyword="k2", channel="ed2k"))
    assert client.connect_calls == 1  # connected only once for two tasks


@pytest.mark.asyncio
async def test_search_failure_arms_channel_backoff(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    client = FakeSearchClient(search_failures=[make_search_failed()])
    worker = SearchWorker("amule-1", client, _deps(catalog, engine, registry, fake_time))
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert registry.is_in_backoff(_ED2K) is True  # channel in backoff
    assert registry.is_in_backoff(_CLIENT) is False  # but not the whole client


@pytest.mark.asyncio
async def test_transport_failure_marks_instance_down(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    # search raises a transport failure (dead stream) → client down + client backoff.
    client = FakeSearchClient(search_failures=[make_unreachable()], results=[(_obs(),)])
    worker = SearchWorker("amule-1", client, _deps(catalog, engine, registry, fake_time))
    await worker.run_task(SearchTask(keyword="k1", channel="ed2k"))
    assert registry.is_in_backoff(_CLIENT) is True
    # After the backoff expires, the next task FORCES a reconnect (down marked).
    fake_time.advance(timedelta(seconds=3.0))
    await worker.run_task(SearchTask(keyword="k2", channel="ed2k"))
    assert client.connect_calls == 2


@pytest.mark.asyncio
async def test_the_client_backoff_grows_until_a_search_succeeds(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    # The adapter's connect() succeeds without touching the network: only a search proves reach.
    fake_time = FakeTime()
    registry = _registry(fake_time)
    client = FakeSearchClient(search_failures=[make_unreachable()] * 4, results=[(_obs(),)])
    worker = SearchWorker("amule-1", client, _deps(catalog, engine, registry, fake_time))
    delays = []
    for _ in range(4):
        await worker.run_task(SearchTask(keyword="k", channel="ed2k"))
        delays.append(registry.time_until_retry(_CLIENT))
        fake_time.advance(registry.time_until_retry(_CLIENT))
    assert delays == [timedelta(seconds=seconds) for seconds in (2, 4, 8, 16)]
    await worker.run_task(SearchTask(keyword="k", channel="ed2k"))
    assert _CLIENT not in registry.snapshot()


@pytest.mark.asyncio
async def test_a_task_is_one_search_given_the_cores_budget(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    fake_time = FakeTime()
    client = FakeSearchClient(results=[(_obs(),)])
    worker = SearchWorker(
        "amule-1", client, _deps(catalog, engine, _registry(fake_time), fake_time)
    )
    await worker.run_task(SearchTask(keyword="keroro", channel="kad"))
    assert client.searches == [("keroro", "kad")]
    assert client.budgets == [SEARCH_BUDGET_SECONDS] == [120.0]


# --- observability event emission (Plan E.2) ---


@pytest.mark.asyncio
async def test_successful_search_emits_search_executed_with_network_and_counts(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    # A successful ed2k search emits SearchExecuted FIRST, labelled with its client,
    # before the per-observation events (ObservationRecorded/DecisionsRecorded).
    fake_time = FakeTime()
    telemetry = RecordingTelemetry()
    client = FakeSearchClient(results=[(_obs(),)], skipped_result_count=2)
    deps = _deps(catalog, engine, _registry(fake_time), fake_time, telemetry=telemetry)
    worker = SearchWorker("amule-1", client, deps)
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert telemetry.events[0] == SearchExecuted(
        client_name="amule-1", channel="ed2k", observation_count=1, skipped_result_count=2
    )
    kinds = [type(e).__name__ for e in telemetry.events]
    assert kinds == ["SearchExecuted", "ObservationRecorded", "DecisionsRecorded"]
    assert telemetry.events[1] == ObservationRecorded(client_name="amule-1", channel="ed2k")


@pytest.mark.asyncio
async def test_search_failure_emits_search_failed(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    # An application-level channel failure (SearchFailedError) emits
    # SearchFailed(client, network).
    fake_time = FakeTime()
    telemetry = RecordingTelemetry()
    client = FakeSearchClient(search_failures=[make_search_failed()])
    deps = _deps(catalog, engine, _registry(fake_time), fake_time, telemetry=telemetry)
    worker = SearchWorker("amule-1", client, deps)
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert telemetry.events == [SearchFailed(client_name="amule-1", channel="ed2k")]


@pytest.mark.asyncio
async def test_connect_failure_emits_instance_unreachable(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    # A connection failure (unreachable daemon) emits ClientUnreachable.
    fake_time = FakeTime()
    telemetry = RecordingTelemetry()
    client = FakeSearchClient(connect_failures=[make_unreachable()])
    deps = _deps(catalog, engine, _registry(fake_time), fake_time, telemetry=telemetry)
    worker = SearchWorker("amule-1", client, deps)
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert telemetry.events == [ClientUnreachable("amule-1")]


@pytest.mark.asyncio
async def test_transport_failure_during_search_emits_instance_unreachable(
    catalog: SqliteCatalogRepository, engine: MatchingEngine
) -> None:
    # A transport failure during search (dead stream) emits ClientUnreachable.
    fake_time = FakeTime()
    telemetry = RecordingTelemetry()
    client = FakeSearchClient(search_failures=[make_unreachable()], results=[(_obs(),)])
    deps = _deps(catalog, engine, _registry(fake_time), fake_time, telemetry=telemetry)
    worker = SearchWorker("amule-1", client, deps)
    await worker.run_task(SearchTask(keyword="keroro", channel="ed2k"))
    assert telemetry.events == [ClientUnreachable("amule-1")]


@pytest.mark.asyncio
async def test_a_search_logs_on_the_worker_logger_and_a_failed_observation_on_its_own(
    catalog: SqliteCatalogRepository,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    catalog_connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON observations"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    fake_time = FakeTime()
    logger, observation_logger = FakeLogger(), FakeLogger()
    client = FakeSearchClient(results=[(_obs(),)])
    deps = _deps(
        catalog,
        engine,
        _registry(fake_time),
        fake_time,
        logger=logger,
        observation_logger=observation_logger,
    )

    await SearchWorker("amule-1", client, deps).run_task(SearchTask("keroro", "ed2k"))

    assert logger.lines == [
        LoggedLine("info", "client amule-1 connected"),
        LoggedLine("info", "client amule-1: 'keroro'/ed2k → 0 verdict(s) changed"),
    ]
    assert [line.level for line in observation_logger.lines] == ["error"]
