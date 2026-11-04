"""What an unexpected exception in each runtime part does today. Each test asserts the CURRENT
behaviour, so a pass is a proof of it, not an endorsement."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from p2pwatch.application.ports.driving.node_metric_lister import NodeMetricLister
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.loop_supervisor import LoopSupervisor
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.search_task_runner import SearchTaskRunner
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.application.steps.status_loop import StatusLoop
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.observability.events import CrawlerStarted, SearchExecuted
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.search.answer import SearchAnswer
from tests.adapters.driving.webui.test_app import _app_on_fakes
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore
from tests.fakes.adapters.driven.fake_raising_notifier import FakeRaisingNotifier
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_search_client import FakeSearchClient
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_cycle import HASH_A, NODE_ID, build_cycle, status
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

_POLICY = BackoffPolicy(base_seconds=2.0, cap_seconds=300.0, factor=2.0, jitter_ratio=0.0)
_FILE = FileKey(network=Network.ED2K, native_id="31d6cfe0d16ae931b73c59d7e0c089c0")


def _reported_file() -> ReportedFile:
    return ReportedFile(
        file=_FILE, filename="a.avi", size_bytes=1, source_count=1, keyword=Keyword("keroro")
    )


class _KadBrokenClient(FakeSearchClient):
    """ed2k answers; kad raises ``error`` on every search."""

    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error
        self.ed2k_searches = 0

    async def search(
        self, keyword: Keyword, *, channel: Channel, budget_seconds: float
    ) -> SearchAnswer:
        if channel == Channel("kad"):
            await asyncio.sleep(0.01)  # noqa: TID251  # ed2k gets some rounds first
            raise self._error
        self.ed2k_searches += 1
        await asyncio.sleep(0)  # noqa: TID251
        return SearchAnswer(reported_files=(), skipped_result_count=0)


def _runner(client: FakeSearchClient, fake_time: FakeTime) -> SearchTaskRunner:
    backoff = BackoffRegistry(
        _POLICY,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        jitter_generator=FakeJitterGenerator(),
        backoff_state_reader=FakeBackoffStateStore(),
    )
    worker = SearchWorker(
        client_name=ClientName("amuled"),
        client=client,
        backoff=backoff,
        cataloguer=None,  # type: ignore[arg-type]  # no reported file: never reached
        observability_dispatcher=ObservabilityOverFakes().dispatcher,
        logger=FakeLogger(),
    )
    return SearchTaskRunner(
        workers=[worker],
        keywords=["keroro", "titar"],
        run_state_reader=FakeRunStateStore(),
        backoff=backoff,
        backoff_state_writer=FakeBackoffStateStore(),
        monotonic_clock=fake_time.monotonic,
        logger=FakeLogger(),
    )


@pytest.mark.asyncio
async def test_loop_supervisor_one_failing_loop_cancels_every_other_and_escapes() -> None:
    cancelled: list[str] = []

    async def healthy() -> None:
        try:
            await asyncio.sleep(3600)  # noqa: TID251
        except asyncio.CancelledError:
            cancelled.append("healthy")
            raise

    async def failing() -> None:
        await asyncio.sleep(0)  # noqa: TID251
        raise RuntimeError("bug in one loop")

    supervisor = LoopSupervisor(run_state_reader=FakeRunStateStore())
    with pytest.raises(ExceptionGroup) as raised:
        await supervisor.supervise([healthy, failing], arm_shutdown_bound=lambda: None)
    assert raised.group_contains(RuntimeError)
    assert cancelled == ["healthy"]


@pytest.mark.asyncio
async def test_a_kad_bug_stops_the_working_ed2k_tasks_too() -> None:
    client = _KadBrokenClient(RuntimeError("unexpected payload"))
    with pytest.raises(ExceptionGroup) as raised:
        await _runner(client, FakeTime()).run(NodeId("n1"))
    assert raised.group_contains(RuntimeError)
    searches_at_stop = client.ed2k_searches
    assert searches_at_stop > 0  # ed2k worked, and stopped with kad
    print(f"ed2k searches before the kad bug ended them: {searches_at_stop}")


@pytest.mark.asyncio
async def test_an_auth_refusal_on_one_channel_stops_the_runner() -> None:
    client = _KadBrokenClient(ClientAuthError("password refused"))
    with pytest.raises(ExceptionGroup) as raised:
        await _runner(client, FakeTime()).run(NodeId("n1"))
    assert raised.group_contains(ClientAuthError)


class _BrokenStatusClient:
    async def status(self) -> object:
        raise KeyError("channels")


@pytest.mark.asyncio
async def test_status_loop_an_unexpected_error_escapes() -> None:
    fake_time = FakeTime()
    loop = StatusLoop(
        client_name=ClientName("amuled"),
        client=_BrokenStatusClient(),  # type: ignore[arg-type]
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        observability_dispatcher=ObservabilityOverFakes().dispatcher,
        run_state_reader=FakeRunStateStore(),
        status_reading_writer=FakeStatusReadingStore((ClientName("amuled"),)),
    )
    with pytest.raises(KeyError):
        await loop.run(NodeId("n1"))


@pytest.mark.asyncio
async def test_download_cycle_documented_never_raises_but_a_listing_bug_escapes() -> None:
    cycle = build_cycle(
        client=FakeDownloadClient(list_failures=[ValueError("bad row")]),
        tracked_download_store=FakeTrackedDownloadStore(),
    )
    with pytest.raises(ValueError):
        await cycle.run(NODE_ID)


@pytest.mark.asyncio
async def test_download_cycle_a_source_read_bug_escapes() -> None:
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    cycle = build_cycle(
        client=FakeDownloadClient(listed=[(status(HASH_A),)]),
        source_client=FakeSourceClient(source_failures=[TypeError("bad source row")]),
        tracked_download_store=tracked_download_store,
    )
    with pytest.raises(TypeError):
        await cycle.run(NODE_ID)


@pytest.mark.asyncio
async def test_dispatcher_absorbs_a_notifier_bug_and_logs_it() -> None:
    logger = FakeLogger()
    dispatcher = ObservabilityDispatcher(
        logger=logger,
        node_metric_writer=FakeNodeMetricStore(),
        notifier=FakeRaisingNotifier(),
        notification_timeout_seconds=5.0,
    )
    await dispatcher.dispatch(CrawlerStarted(download_enabled=False, node_id=NodeId("n1")))
    assert any("notification operations failed" in str(line) for line in logger.lines)


class _BrokenMetricStore(FakeNodeMetricStore):
    def record_increment(self, increment: object) -> None:  # type: ignore[override]
        raise RuntimeError("metric store bug")


@pytest.mark.asyncio
async def test_dispatcher_lets_a_node_metric_bug_escape_to_the_searching_caller() -> None:
    dispatcher = ObservabilityDispatcher(
        logger=FakeLogger(),
        node_metric_writer=_BrokenMetricStore(),
        notifier=FakeRaisingNotifier(),
        notification_timeout_seconds=5.0,
    )
    with pytest.raises(RuntimeError):
        await dispatcher.dispatch(
            SearchExecuted(
                client_name=ClientName("amuled"),
                channel=Channel("ed2k"),
                observation_count=0,
                skipped_result_count=0,
            )
        )


class _BuggyObservationWriter:
    def record_observation(self, observation: FileObservation) -> None:
        raise TypeError("not a StoreError")


@pytest.mark.asyncio
async def test_cataloguer_absorbs_only_store_errors() -> None:
    fake_time = FakeTime()
    cataloguer = Cataloguer(
        observation_writer=_BuggyObservationWriter(),  # type: ignore[arg-type]
        file_judge=None,  # type: ignore[arg-type]
        observability_dispatcher=ObservabilityOverFakes().dispatcher,
        wall_clock=fake_time.wall,
        logger=FakeLogger(),
    )
    with pytest.raises(TypeError):
        await cataloguer.catalog(
            _reported_file(),
            client_name=ClientName("amuled"),
            channel=Channel("ed2k"),
            node_id=NodeId("n1"),
        )


class _OneFileScan:
    def read_file_count(self) -> int:
        return 1

    def iter_latest_observations(self) -> Iterator[FileObservation]:
        yield FileObservation(
            reported_file=_reported_file(),
            observed_at=datetime(2026, 11, 1, tzinfo=UTC),
            node_id=NodeId("n1"),
        )


class _BuggyJudge:
    async def rejudge(self, *args: object, **kwargs: object) -> int:
        raise RuntimeError("file judged without an observation")


@pytest.mark.asyncio
async def test_reevaluation_a_non_store_error_on_one_file_stops_the_start() -> None:
    fingerprints = FakePolicyFingerprintStore(stored_fingerprint="old")
    reevaluator = CatalogReevaluator(
        policy_fingerprint="new",
        policy_fingerprint_reader=fingerprints,
        policy_fingerprint_writer=fingerprints,
        file_judge=_BuggyJudge(),  # type: ignore[arg-type]
        catalog_scan_reader=_OneFileScan(),  # type: ignore[arg-type]
        progress_every_files=200,
        logger=FakeLogger(),
    )
    with pytest.raises(RuntimeError):
        await reevaluator.reevaluate_if_policy_changed(NodeId("n1"))
    assert fingerprints.read_policy_fingerprint() == "old"  # retried, and failed, at every start


class _BrokenLister(NodeMetricLister):
    def list_node_metrics(self) -> object:  # type: ignore[override]
        raise RuntimeError("metrics bug")


@pytest.mark.asyncio
async def test_webui_a_handler_bug_is_a_500_and_the_app_keeps_serving() -> None:
    app = _app_on_fakes(node_metric_lister=_BrokenLister())
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        metrics = await client.get("/metrics")
        health = await client.get("/health")
    assert metrics.status_code == 500
    assert (health.status_code, health.json()) == (200, {"status": "ok"})

