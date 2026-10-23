"""The crawler starts under the node's id, re-evaluates a changed policy, then runs its loops."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import timedelta

import pytest

from p2pwatch.application.crawler_lifecycle import CrawlerLifecycle
from p2pwatch.application.steps.reevaluate_catalog import ReevaluationSummary
from p2pwatch.application.steps.search_worker import BackoffPolicy, BackoffRegistry
from p2pwatch.domain.observability.events import CrawlerStarted
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_node_id_generator import FakeNodeIdGenerator
from tests.fakes.adapters.driven.fake_node_id_store import FakeNodeIdStore
from tests.fakes.adapters.driven.fake_policy_fingerprint_store import FakePolicyFingerprintStore
from tests.fakes.adapters.driven.fake_time import FakeTime

_FINGERPRINT = "policy-2"
_KAD = BackoffKey("amuled", "kad")
_POLICY = BackoffPolicy(base_seconds=2.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0)


class _Crawl:
    """A ``CrawlerLifecycle`` over fakes: two loops record their node id, then wait for the stop."""

    def __init__(
        self,
        *,
        configured_node_id: str | None = None,
        stored_fingerprint: str | None = _FINGERPRINT,
        download_enabled: bool = False,
    ) -> None:
        self.steps: list[str] = []
        self.backoff_states_seen_by_loops: list[dict[BackoffKey, BackoffState]] = []
        self.event_emitter = FakeEventEmitter()
        self.fingerprints = FakePolicyFingerprintStore(stored_fingerprint=stored_fingerprint)
        self.logger = FakeLogger()
        self.reevaluation_gate_logger = FakeLogger()
        self.shutdown = asyncio.Event()
        fake_time = FakeTime()
        self.backoff_state_store = FakeBackoffStateStore()
        self.backoff = BackoffRegistry(
            _POLICY, fake_time.wall, fake_time.monotonic, FakeJitterGenerator()
        )
        self._loops_started = 0
        self._both_loops_started = asyncio.Event()
        self.crawler_lifecycle = CrawlerLifecycle(
            configured_node_id=configured_node_id,
            node_id_reader=FakeNodeIdStore(stored_node_id="stored-node"),
            node_id_writer=FakeNodeIdStore(stored_node_id=None),
            node_id_generator=FakeNodeIdGenerator("new-node"),
            wall_clock=fake_time.wall,
            event_emitter=self.event_emitter,
            policy_fingerprint=_FINGERPRINT,
            policy_fingerprint_reader=self.fingerprints,
            policy_fingerprint_writer=self.fingerprints,
            reevaluate=self._reevaluate,
            backoff=self.backoff,
            backoff_state_reader=self.backoff_state_store,
            loops=[self._loop("search"), self._loop("status")],
            download_enabled=download_enabled,
            shutdown=self.shutdown,
            logger=self.logger,
            reevaluation_gate_logger=self.reevaluation_gate_logger,
        )

    async def _reevaluate(self, node_id: str) -> ReevaluationSummary:
        self.steps.append(
            f"reevaluated under {node_id}, {len(self.event_emitter.events)} event(s) out"
        )
        return ReevaluationSummary(files_evaluated=3, rows_written=1)

    def _loop(self, name: str) -> Callable[[str], Coroutine[object, object, None]]:
        async def loop(node_id: str) -> None:
            self.steps.append(f"{name} under {node_id}")
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
        self.shutdown.set()
        await asyncio.wait_for(run, 1.0)


@pytest.mark.asyncio
async def test_the_crawler_starts_under_the_stored_node_id_and_runs_each_loop_with_it() -> None:
    crawl = _Crawl()

    await crawl.run_until_both_loops_start_then_stop()

    assert crawl.logger.lines == [LoggedLine("info", "crawler started: node_id=stored-node")]
    assert crawl.event_emitter.events == [CrawlerStarted(download_enabled=False)]
    assert crawl.event_emitter.node_ids == {"stored-node"}
    assert crawl.steps == ["search under stored-node", "status under stored-node", "bound armed"]


@pytest.mark.asyncio
async def test_a_configured_node_id_and_the_download_loop_show_in_the_start() -> None:
    crawl = _Crawl(configured_node_id="forced-node", download_enabled=True)

    await crawl.run_until_both_loops_start_then_stop()

    assert crawl.logger.lines == [
        LoggedLine("info", "crawler started: node_id=forced-node"),
        LoggedLine("info", "download enabled: download loop armed"),
    ]
    assert crawl.event_emitter.events == [CrawlerStarted(download_enabled=True)]
    assert crawl.event_emitter.node_ids == {"forced-node"}


@pytest.mark.asyncio
async def test_a_changed_policy_is_re_evaluated_under_the_node_id_after_the_start() -> None:
    crawl = _Crawl(stored_fingerprint="policy-1")

    await crawl.run_until_both_loops_start_then_stop()

    assert crawl.steps[0] == "reevaluated under stored-node, 1 event(s) out"
    assert crawl.steps[1:] == [
        "search under stored-node",
        "status under stored-node",
        "bound armed",
    ]
    assert crawl.fingerprints.stored_fingerprint == _FINGERPRINT
    assert crawl.reevaluation_gate_logger.lines == [
        LoggedLine("info", "catalogue re-evaluated: 3 files, 1 rows written")
    ]


@pytest.mark.asyncio
async def test_the_backoff_waits_the_previous_run_saved_are_resumed_before_the_loops() -> None:
    crawl = _Crawl()
    started_at = FakeTime().wall.now() - timedelta(seconds=100)
    saved = {_KAD: BackoffState(1, started_at, timedelta(seconds=300))}
    crawl.backoff_state_store.set_backoff_states(saved)

    await crawl.run_until_both_loops_start_then_stop()

    assert crawl.backoff_states_seen_by_loops == [saved, saved]
    assert crawl.backoff.time_until_retry(_KAD) == timedelta(seconds=200)
