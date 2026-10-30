import sqlite3
from datetime import timedelta

import pytest

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.persistence_sqlite.micros import instant_to_micros
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.search_worker import (
    SEARCH_BUDGET_SECONDS,
    SearchTask,
    SearchWorker,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.observability.node_metric import NodeCounter, NodeMetricSample
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.search.backoff import BackoffKey
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_search_client import (
    FakeSearchClient,
    make_search_failed,
    make_unreachable,
)
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.catalog_rows import (
    count_decisions,
    count_observations,
    decision_node_ids,
    observation_node_ids,
)

_NODE_ID = NodeId("n1")
_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_DL_NAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"
_CLIENT = BackoffKey(client_name=ClientName("amule-1"), channel=None)
_KAD = BackoffKey(client_name=ClientName("amule-1"), channel=Channel("kad"))
_ED2K = BackoffKey(client_name=ClientName("amule-1"), channel=Channel("ed2k"))

# jitter_ratio 0.0 + FakeJitterGenerator(jitter_value=0.0) → backoff = exact NOMINAL delay.
_POLICY = BackoffPolicy(
    base_seconds=2.0,
    cap_seconds=60.0,
    factor=2.0,
    jitter_ratio=0.0,
)


def _reported_file() -> ReportedFile:
    return ReportedFile(
        file=FileKey(network=Network.ED2K, native_id=_HASH),
        filename=_DL_NAME,
        size_bytes=234_000_000,
        source_count=3,
        keyword=Keyword("keroro"),
    )


def _registry(fake_time: FakeTime) -> BackoffRegistry:
    return BackoffRegistry(
        _POLICY, fake_time.wall, fake_time.monotonic, FakeJitterGenerator(), FakeBackoffStateStore()
    )


def _worker(
    client: FakeSearchClient,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    backoff: BackoffRegistry,
    fake_time: FakeTime,
    *,
    observability_dispatcher: ObservabilityDispatcher | None = None,
    logger: FakeLogger | None = None,
    cataloguer_logger: FakeLogger | None = None,
) -> SearchWorker:
    dispatcher = observability_dispatcher or ObservabilityOverFakes().dispatcher
    file_judge = FileJudge(
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        engine=engine,
        waker=FakeWaker(),
        observability_dispatcher=dispatcher,
        wall_clock=fake_time.wall,
    )
    cataloguer = Cataloguer(
        observation_writer=observation_store,
        file_judge=file_judge,
        observability_dispatcher=dispatcher,
        wall_clock=fake_time.wall,
        logger=cataloguer_logger or FakeLogger(),
    )
    return SearchWorker(
        client_name=ClientName("amule-1"),
        client=client,
        backoff=backoff,
        cataloguer=cataloguer,
        observability_dispatcher=dispatcher,
        logger=logger or FakeLogger(),
    )


def test_a_worker_declares_the_channels_of_its_client(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    client = FakeSearchClient(channels=(Channel("kad"),))
    worker = _worker(
        client, observation_store, decision_store, engine, _registry(fake_time), fake_time
    )
    assert worker.channels == ("kad",)


@pytest.mark.parametrize(
    ("failed", "ready_in_seconds"),
    [((), 0), ((_CLIENT,), 2), ((_KAD,), 2), ((_ED2K,), 0)],
)
def test_a_worker_is_ready_for_a_channel_when_neither_it_nor_the_channel_is_backed_off(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    failed: tuple[BackoffKey, ...],
    ready_in_seconds: int,
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    for key in failed:
        registry.record_failure(key)
    worker = _worker(
        FakeSearchClient(), observation_store, decision_store, engine, registry, fake_time
    )
    assert worker.time_until_ready(Channel("kad")) == timedelta(seconds=ready_in_seconds)
    fake_time.advance(timedelta(seconds=3.0))
    assert worker.time_until_ready(Channel("kad")) == timedelta(0)  # a past backoff is no wait


def test_a_worker_waits_for_the_later_of_its_two_backoffs(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.advance(timedelta(seconds=1.0))
    registry.record_failure(_CLIENT)
    worker = _worker(
        FakeSearchClient(), observation_store, decision_store, engine, registry, fake_time
    )
    assert worker.time_until_ready(Channel("kad")) == timedelta(seconds=2)
    fake_time.advance(timedelta(seconds=1.5))
    registry.reset(_CLIENT)
    assert worker.time_until_ready(Channel("kad")) == timedelta(0)  # the channel's own ended first


# --- SearchWorker ---


@pytest.mark.asyncio
async def test_successful_task_records_observation(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    client = FakeSearchClient(results=[(_reported_file(),)])
    worker = _worker(
        client, observation_store, decision_store, engine, _registry(fake_time), fake_time
    )
    await worker.run_task(SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k")), _NODE_ID)
    assert client.searches == [("keroro", "ed2k")]
    assert count_decisions(catalog_connection) == 1
    assert rows(catalog_connection, "SELECT observed_at_micros FROM observations") == [
        {"observed_at_micros": instant_to_micros(fake_time.wall.now())}
    ]
    assert observation_node_ids(catalog_connection) == decision_node_ids(catalog_connection)
    assert decision_node_ids(catalog_connection) == {_NODE_ID}


@pytest.mark.asyncio
async def test_multiple_observations_some_unchanged_are_all_processed(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    discarded = ReportedFile(
        file=FileKey(network=Network.ED2K, native_id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
        filename="random.txt",  # discarded by the engine → catalog returns 0
        size_bytes=10,
        source_count=1,
        keyword=Keyword("keroro"),
    )
    # Two observations in the same readout: the 1st is discarded (False → loop back), the 2nd
    # changes a verdict. Covers the "if False → next observation" edge.
    client = FakeSearchClient(results=[(discarded, _reported_file())])
    worker = _worker(
        client, observation_store, decision_store, engine, _registry(fake_time), fake_time
    )
    await worker.run_task(SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k")), _NODE_ID)
    assert count_observations(catalog_connection) == 2
    assert count_decisions(catalog_connection) == 1


@pytest.mark.asyncio
async def test_backoff_expires_and_item_runs_again(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)  # 2.0s
    client = FakeSearchClient(results=[(_reported_file(),)])
    worker = _worker(client, observation_store, decision_store, engine, registry, fake_time)
    fake_time.advance(timedelta(seconds=3.0))  # the channel is no longer in backoff
    await worker.run_task(SearchTask(keyword=Keyword("k"), channel=Channel("kad")), _NODE_ID)
    assert client.searches == [("k", "kad")]


@pytest.mark.asyncio
async def test_search_failure_arms_channel_backoff(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    client = FakeSearchClient(search_failures=[make_search_failed()])
    worker = _worker(client, observation_store, decision_store, engine, registry, fake_time)
    await worker.run_task(SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k")), _NODE_ID)
    assert registry.is_in_backoff(_ED2K) is True  # channel in backoff
    assert registry.is_in_backoff(_CLIENT) is False  # but not the whole client


@pytest.mark.asyncio
async def test_transport_failure_marks_instance_down(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    # search raises a transport failure (dead stream) → client down + client backoff.
    client = FakeSearchClient(search_failures=[make_unreachable()], results=[(_reported_file(),)])
    worker = _worker(client, observation_store, decision_store, engine, registry, fake_time)
    await worker.run_task(SearchTask(keyword=Keyword("k1"), channel=Channel("ed2k")), _NODE_ID)
    assert registry.is_in_backoff(_CLIENT) is True
    fake_time.advance(timedelta(seconds=3.0))
    await worker.run_task(SearchTask(keyword=Keyword("k2"), channel=Channel("ed2k")), _NODE_ID)
    assert client.searches == [("k1", "ed2k"), ("k2", "ed2k")]  # searched again once it expires


@pytest.mark.asyncio
async def test_the_client_backoff_grows_until_a_search_succeeds(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    client = FakeSearchClient(
        search_failures=[make_unreachable()] * 4, results=[(_reported_file(),)]
    )
    worker = _worker(client, observation_store, decision_store, engine, registry, fake_time)
    delays = []
    for _ in range(4):
        await worker.run_task(SearchTask(keyword=Keyword("k"), channel=Channel("ed2k")), _NODE_ID)
        delays.append(registry.time_until_retry(_CLIENT))
        fake_time.advance(registry.time_until_retry(_CLIENT))
    assert delays == [timedelta(seconds=seconds) for seconds in (2, 4, 8, 16)]
    await worker.run_task(SearchTask(keyword=Keyword("k"), channel=Channel("ed2k")), _NODE_ID)
    assert _CLIENT not in registry.snapshot()


@pytest.mark.asyncio
async def test_a_task_is_one_search_given_the_cores_budget(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    fake_time = FakeTime()
    client = FakeSearchClient(results=[(_reported_file(),)])
    worker = _worker(
        client, observation_store, decision_store, engine, _registry(fake_time), fake_time
    )
    await worker.run_task(SearchTask(keyword=Keyword("keroro"), channel=Channel("kad")), _NODE_ID)
    assert client.searches == [("keroro", "kad")]
    assert client.budgets == [SEARCH_BUDGET_SECONDS] == [120.0]


# --- observability event dispatch (Plan E.2) ---


@pytest.mark.asyncio
async def test_successful_search_emits_search_executed_with_network_and_counts(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    # A successful ed2k search dispatches SearchExecuted FIRST, labelled with its client,
    # before the per-observation events (ObservationRecorded, DecisionsRecorded).
    fake_time = FakeTime()
    observability = ObservabilityOverFakes()
    client = FakeSearchClient(results=[(_reported_file(),)], skipped_result_count=2)
    worker = _worker(
        client,
        observation_store,
        decision_store,
        engine,
        _registry(fake_time),
        fake_time,
        observability_dispatcher=observability.dispatcher,
    )
    await worker.run_task(SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k")), _NODE_ID)
    assert observability.logger.lines == [
        LoggedLine("debug", "search ed2k: 1 observation(s)"),
        LoggedLine("debug", "observation recorded (ed2k)"),
        LoggedLine("info", f"decisions for {_DL_NAME} ({_HASH}): 062A none → download"),
    ]
    labels = (("client", "amule-1"), ("channel", "ed2k"))
    assert set(observability.node_metric_store.read_samples()) == {
        NodeMetricSample(node_metric=NodeCounter.SEARCHES, labels=labels, value=1.0),
        NodeMetricSample(node_metric=NodeCounter.SEARCH_RESULTS_SKIPPED, labels=labels, value=2.0),
        NodeMetricSample(node_metric=NodeCounter.OBSERVATIONS, labels=labels, value=1.0),
        NodeMetricSample(
            node_metric=NodeCounter.DECISIONS, labels=(("tier", "download"),), value=1.0
        ),
    }
    assert observability.notifier.node_ids == [_NODE_ID]


@pytest.mark.asyncio
async def test_search_failure_dispatches_search_failed(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    # An application-level channel failure (SearchFailedError) dispatches
    # SearchFailed(client, channel).
    fake_time = FakeTime()
    observability = ObservabilityOverFakes()
    client = FakeSearchClient(search_failures=[make_search_failed()])
    worker = _worker(
        client,
        observation_store,
        decision_store,
        engine,
        _registry(fake_time),
        fake_time,
        observability_dispatcher=observability.dispatcher,
    )
    await worker.run_task(SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k")), _NODE_ID)
    assert observability.logger.lines == [LoggedLine("warning", "search failed on ed2k")]
    assert observability.node_metric_store.read_samples() == (
        NodeMetricSample(
            node_metric=NodeCounter.SEARCH_FAILURES,
            labels=(("client", "amule-1"), ("channel", "ed2k")),
            value=1.0,
        ),
    )


@pytest.mark.asyncio
async def test_transport_failure_during_search_dispatches_client_unreachable(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> None:
    # A transport failure during search (dead stream) dispatches ClientUnreachable.
    fake_time = FakeTime()
    observability = ObservabilityOverFakes()
    client = FakeSearchClient(search_failures=[make_unreachable()], results=[(_reported_file(),)])
    worker = _worker(
        client,
        observation_store,
        decision_store,
        engine,
        _registry(fake_time),
        fake_time,
        observability_dispatcher=observability.dispatcher,
    )
    await worker.run_task(SearchTask(keyword=Keyword("keroro"), channel=Channel("ed2k")), _NODE_ID)
    assert observability.logger.lines == [LoggedLine("warning", "amule-1 unreachable")]
    assert observability.node_metric_store.read_samples() == (
        NodeMetricSample(
            node_metric=NodeCounter.CLIENT_UNREACHABLE, labels=(("client", "amule-1"),), value=1.0
        ),
    )


@pytest.mark.asyncio
async def test_a_search_logs_on_the_worker_logger_and_a_failed_observation_on_its_own(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_connection: sqlite3.Connection,
    engine: MatchingEngine,
) -> None:
    catalog_connection.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON observations"
        " BEGIN SELECT RAISE(ABORT, 'injected failure'); END"
    )
    fake_time = FakeTime()
    logger, cataloguer_logger = FakeLogger(), FakeLogger()
    client = FakeSearchClient(results=[(_reported_file(),)])
    worker = _worker(
        client,
        observation_store,
        decision_store,
        engine,
        _registry(fake_time),
        fake_time,
        logger=logger,
        cataloguer_logger=cataloguer_logger,
    )

    await worker.run_task(SearchTask(Keyword("keroro"), Channel("ed2k")), _NODE_ID)

    assert logger.lines == [
        LoggedLine("info", "client amule-1: 'keroro'/ed2k → 0 verdict(s) changed"),
    ]
    assert [line.level for line in cataloguer_logger.lines] == ["error"]
