"""The crawler starts under the node's id, re-evaluates a changed policy, then runs its loops."""

import asyncio
from datetime import timedelta

import pytest

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.crawler_lifecycle import CrawlerLifecycle, NodeLoop
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.loop_supervisor import LoopSupervisor
from p2pwatch.application.steps.node_id_resolver import NodeIdResolver
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_node_id_generator import FakeNodeIdGenerator
from tests.fakes.adapters.driven.fake_node_id_store import FakeNodeIdStore
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

_FINGERPRINT = "policy-2"
_KAD = BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad"))
_POLICY = BackoffPolicy(base_seconds=2.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0)
_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_FILENAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"


class _Crawl:
    """A ``CrawlerLifecycle`` over its real steps, the stores real, the rest fakes: two loops
    record their node id, then wait for the stop."""

    def __init__(
        self,
        observation_store: SqliteObservationStore,
        decision_store: SqliteDecisionStore,
        catalog_scan_reader: SqliteCatalogScanReader,
        engine: MatchingEngine,
        *,
        stored_fingerprint: str | None = _FINGERPRINT,
        download_enabled: bool = False,
    ) -> None:
        self.steps: list[str] = []
        self.backoff_states_seen_by_loops: list[dict[BackoffKey, BackoffState]] = []
        self.observability = ObservabilityOverFakes()
        self.fingerprints = FakePolicyFingerprintStore(stored_fingerprint=stored_fingerprint)
        self.logger = FakeLogger()
        self.catalog_reevaluator_logger = FakeLogger()
        self.run_state = FakeRunStateStore()
        self.fake_time = FakeTime()
        self.backoff_state_store = FakeBackoffStateStore()
        self.backoff = BackoffRegistry(
            _POLICY,
            wall_clock=self.fake_time.wall,
            monotonic_clock=self.fake_time.monotonic,
            jitter_generator=FakeJitterGenerator(),
            backoff_state_reader=self.backoff_state_store,
        )
        self._loops_started = 0
        self._both_loops_started = asyncio.Event()
        self.crawler_lifecycle = CrawlerLifecycle(
            node_id_resolver=NodeIdResolver(
                node_id_reader=FakeNodeIdStore(stored_node_id=NodeId("stored-node")),
                node_id_writer=FakeNodeIdStore(stored_node_id=None),
                node_id_generator=FakeNodeIdGenerator(NodeId("new-node")),
                wall_clock=self.fake_time.wall,
            ),
            observability_dispatcher=self.observability.dispatcher,
            catalog_reevaluator=CatalogReevaluator(
                policy_fingerprint=_FINGERPRINT,
                policy_fingerprint_reader=self.fingerprints,
                policy_fingerprint_writer=self.fingerprints,
                file_judge=FileJudge(
                    observation_reader=observation_store,
                    decision_writer=decision_store,
                    decision_reader=decision_store,
                    engine=engine,
                    waker=FakeWaker(),
                    observability_dispatcher=self.observability.dispatcher,
                    wall_clock=self.fake_time.wall,
                ),
                catalog_scan_reader=catalog_scan_reader,
                progress_every_files=200,
                logger=self.catalog_reevaluator_logger,
            ),
            backoff=self.backoff,
            loops=[self._loop("search"), self._loop("status")],
            download_enabled=download_enabled,
            loop_supervisor=LoopSupervisor(run_state_reader=self.run_state),
            logger=self.logger,
        )

    def _loop(self, name: str) -> NodeLoop:
        async def loop(node_id: NodeId) -> None:
            self.steps.append(
                f"{name} under {node_id}, {len(self.observability.logger.lines)} event(s) out"
            )
            self.backoff_states_seen_by_loops.append(self.backoff.snapshot())
            self._loops_started += 1
            if self._loops_started == 2:
                self._both_loops_started.set()
            await asyncio.Event().wait()

        return loop

    async def run_until_both_loops_start_then_stop(self) -> None:
        run = asyncio.create_task(
            self.crawler_lifecycle.run(arm_shutdown_bound=lambda: self.steps.append("bound armed"))
        )
        await asyncio.wait_for(self._both_loops_started.wait(), 1.0)
        self.run_state.set_shutdown_requested()
        await asyncio.wait_for(run, 1.0)


@pytest.mark.asyncio
async def test_the_crawler_starts_under_the_stored_node_id_and_runs_each_loop_with_it(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(observation_store, decision_store, catalog_scan_reader, engine)

    await crawl.run_until_both_loops_start_then_stop()

    assert crawl.logger.lines == [
        LoggedLine(level="info", message="crawler started: node_id=stored-node")
    ]
    assert crawl.observability.notifier.calls == [
        (
            Audience.OPERATIONS,
            RelayedLogLine(
                message="🟢 node online (download off)",
                severity=Severity.INFO,
                node_id=NodeId("stored-node"),
            ),
        )
    ]
    assert crawl.steps == [
        "search under stored-node, 1 event(s) out",
        "status under stored-node, 1 event(s) out",
        "bound armed",
    ]
    assert crawl.catalog_reevaluator_logger.lines == [
        LoggedLine(level="info", message="policy unchanged: catalogue re-evaluation skipped")
    ]


@pytest.mark.asyncio
async def test_the_download_loop_shows_in_the_start(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(
        observation_store,
        decision_store,
        catalog_scan_reader,
        engine,
        download_enabled=True,
    )

    await crawl.run_until_both_loops_start_then_stop()

    assert crawl.logger.lines == [
        LoggedLine(level="info", message="crawler started: node_id=stored-node"),
        LoggedLine(level="info", message="download enabled: download loop armed"),
    ]
    assert crawl.observability.notifier.calls == [
        (
            Audience.OPERATIONS,
            RelayedLogLine(
                message="🟢 node online (download on)",
                severity=Severity.INFO,
                node_id=NodeId("stored-node"),
            ),
        )
    ]


@pytest.mark.asyncio
async def test_a_changed_policy_is_re_evaluated_under_the_node_id_after_the_start(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(
        observation_store,
        decision_store,
        catalog_scan_reader,
        engine,
        stored_fingerprint="policy-1",
    )
    reported_file = ReportedFile(
        file=FileKey(network=Network.ED2K, native_id=_HASH),
        filename=_FILENAME,
        size_bytes=234_000_000,
        source_count=3,
        keyword=Keyword("keroro"),
    )
    observation_store.record_observation(
        FileObservation(
            reported_file=reported_file,
            observed_at=crawl.fake_time.wall.now(),
            node_id=NodeId("stored-node"),
        )
    )

    await crawl.run_until_both_loops_start_then_stop()

    assert [line.message for line in crawl.observability.logger.lines] == [
        "🟢 node online (download off)",
        f"decisions for {_FILENAME} ({_HASH}): 062A none → download",
    ]
    assert crawl.steps == [
        "search under stored-node, 2 event(s) out",
        "status under stored-node, 2 event(s) out",
        "bound armed",
    ]
    assert crawl.fingerprints.stored_fingerprint == _FINGERPRINT
    assert crawl.catalog_reevaluator_logger.lines == [
        LoggedLine(level="info", message="catalogue re-evaluated: 1 files, 1 rows written")
    ]


@pytest.mark.asyncio
async def test_the_backoff_waits_the_previous_run_saved_are_resumed_before_the_loops(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(observation_store, decision_store, catalog_scan_reader, engine)
    started_at = crawl.fake_time.wall.now() - timedelta(seconds=100)
    saved = {_KAD: BackoffState(attempts=1, started_at=started_at, delay=timedelta(seconds=300))}
    crawl.backoff_state_store.set_backoff_states(saved)

    await crawl.run_until_both_loops_start_then_stop()

    assert crawl.backoff_states_seen_by_loops == [saved, saved]
    assert crawl.backoff.time_until_retry(_KAD) == timedelta(seconds=200)
