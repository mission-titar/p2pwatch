"""The crawler starts under its node id, re-evaluates a changed policy, then runs its works."""

import asyncio
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_scan_reader import (
    SqliteCatalogScanReader,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.crawler_lifecycle import CrawlerLifecycle
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.catalog_reevaluator import CatalogReevaluator
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.supervisor import SupervisedWork, Supervisor
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

_FINGERPRINT = "policy-2"
_NODE_ID = NodeId("titar-node")
_KAD = BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad"))
_POLICY = BackoffPolicy(base_seconds=2.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0)
_HASH = "31d6cfe0d16ae931b73c59d7e0c089c0"
_FILENAME = "Keroro N°062A Les demoiselles cambrioleuses.avi"


class _StartedWork(Work):
    """Tells its crawl it started at its first turn, then waits for the stop."""

    def __init__(self, name: str, *, crawl: "_Crawl") -> None:
        self._name = name
        self._crawl = crawl

    def __str__(self) -> str:
        return self._name

    async def wait_for_next_turn(self) -> None:
        """Waits for nothing."""

    async def run_once(self) -> None:
        self._crawl.work_started(self._name)
        await asyncio.Event().wait()


class _Crawl:
    """A ``CrawlerLifecycle`` over its real steps, the stores real, the rest fakes: two works
    record their start, then wait for the stop."""

    def __init__(
        self,
        observation_store: SqliteObservationStore,
        *,
        decision_store: SqliteDecisionStore,
        catalog_scan_reader: SqliteCatalogScanReader,
        engine: MatchingEngine,
        stored_fingerprint: str | None = _FINGERPRINT,
        download_enabled: bool = False,
    ) -> None:
        self.steps: list[str] = []
        self.backoff_states_seen_by_works: list[dict[BackoffKey, BackoffState]] = []
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
        self._works_started = 0
        self._both_works_started = asyncio.Event()
        self.crawler_lifecycle = CrawlerLifecycle(
            node_id=_NODE_ID,
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
                    node_id=_NODE_ID,
                ),
                catalog_scan_reader=catalog_scan_reader,
                progress_every_files=200,
                run_state_reader=self.run_state,
                monotonic_clock=self.fake_time.monotonic,
                logger=self.catalog_reevaluator_logger,
            ),
            backoff=self.backoff,
            works=[self._work("search"), self._work("status")],
            download_enabled=download_enabled,
            supervisor=Supervisor(
                run_state_reader=self.run_state,
                monotonic_clock=FakeBlockingMonotonicClock(),  # no limit expires
                health_recorder=HealthRecorder(logger=FakeLogger(), subscribers=()),
                restart_policy=RestartPolicy(owners={}, logger=FakeLogger()),
                logger=FakeLogger(),
            ),
            logger=self.logger,
        )

    def _work(self, name: str) -> SupervisedWork:
        return SupervisedWork(
            work=_StartedWork(name, crawl=self),
            time_limit=timedelta(days=1),
            feeds=(
                Component(
                    name=name,
                    labels=ComponentLabels(client_name=ClientName("amuled")),
                    conditions=(BUGS,),
                ),
            ),
        )

    def work_started(self, name: str) -> None:
        self.steps.append(f"{name}, {len(self.observability.logger.lines)} event(s) out")
        self.backoff_states_seen_by_works.append(self.backoff.snapshot())
        self._works_started += 1
        if self._works_started == 2:
            self._both_works_started.set()

    async def run_until_both_works_start_then_stop(self) -> None:
        run = asyncio.create_task(
            self.crawler_lifecycle.run(arm_shutdown_bound=lambda: self.steps.append("bound armed"))
        )
        await asyncio.wait_for(self._both_works_started.wait(), 1.0)
        self.run_state.set_shutdown_requested()
        await asyncio.wait_for(run, 1.0)


@pytest.mark.asyncio
async def test_the_crawler_starts_under_its_node_id_then_runs_each_work(
    *,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(
        observation_store,
        decision_store=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
    )

    await crawl.run_until_both_works_start_then_stop()

    assert crawl.logger.lines == [
        LoggedLine(level="info", message="crawler started: node_id=titar-node")
    ]
    assert crawl.observability.notifier.calls == [
        (
            Audience.OPERATIONS,
            RelayedLogLine(
                message="🟢 node online (download off)",
                severity=Severity.INFO,
                node_id=_NODE_ID,
            ),
        )
    ]
    assert crawl.steps == [
        "search, 1 event(s) out",
        "status, 1 event(s) out",
        "bound armed",
    ]
    assert crawl.catalog_reevaluator_logger.lines == [
        LoggedLine(level="info", message="policy unchanged: catalogue re-evaluation skipped")
    ]


@pytest.mark.asyncio
async def test_the_download_loop_shows_in_the_start(
    *,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(
        observation_store,
        decision_store=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
        download_enabled=True,
    )

    await crawl.run_until_both_works_start_then_stop()

    assert crawl.logger.lines == [
        LoggedLine(level="info", message="crawler started: node_id=titar-node"),
        LoggedLine(level="info", message="download enabled: download loop armed"),
    ]
    assert crawl.observability.notifier.calls == [
        (
            Audience.OPERATIONS,
            RelayedLogLine(
                message="🟢 node online (download on)",
                severity=Severity.INFO,
                node_id=_NODE_ID,
            ),
        )
    ]


@pytest.mark.asyncio
async def test_a_changed_policy_is_re_evaluated_after_the_start(
    *,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(
        observation_store,
        decision_store=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
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
            node_id=_NODE_ID,
        )
    )

    await crawl.run_until_both_works_start_then_stop()

    assert [line.message for line in crawl.observability.logger.lines] == [
        "🟢 node online (download off)",
        f"decisions for {_FILENAME} ({_HASH}): 062A none → download",
    ]
    assert crawl.steps == [
        "search, 2 event(s) out",
        "status, 2 event(s) out",
        "bound armed",
    ]
    assert crawl.fingerprints.stored_fingerprint == _FINGERPRINT
    assert crawl.catalog_reevaluator_logger.lines == [
        LoggedLine(level="info", message="catalogue re-evaluated: 1 files, 1 rows written")
    ]


@pytest.mark.asyncio
async def test_the_backoff_waits_the_previous_run_saved_are_resumed_before_the_works(
    *,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    catalog_scan_reader: SqliteCatalogScanReader,
    engine: MatchingEngine,
) -> None:
    crawl = _Crawl(
        observation_store,
        decision_store=decision_store,
        catalog_scan_reader=catalog_scan_reader,
        engine=engine,
    )
    started_at = crawl.fake_time.wall.now() - timedelta(seconds=100)
    saved = {_KAD: BackoffState(attempts=1, started_at=started_at, delay=timedelta(seconds=300))}
    crawl.backoff_state_store.set_backoff_states(saved)

    await crawl.run_until_both_works_start_then_stop()

    assert crawl.backoff_states_seen_by_works == [saved, saved]
    assert crawl.backoff.time_until_retry(_KAD) == timedelta(seconds=200)
