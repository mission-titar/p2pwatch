"""The crawler starts under the node's id, re-evaluates a changed policy, then runs its loops."""

import asyncio
from collections.abc import Callable, Coroutine

import pytest

from p2pwatch.application.reevaluate_catalog import ReevaluationSummary
from p2pwatch.application.run_crawler import RunCrawler
from p2pwatch.domain.observability.events import CrawlerStarted
from p2pwatch.ports.driven.policy_fingerprint import (
    PolicyFingerprintReader,
    PolicyFingerprintWriter,
)
from p2pwatch_testing.application.fakes import (
    FakeEventEmitter,
    FakeLogger,
    FakeNodeIdGenerator,
    FakeNodeIdStore,
    FakeTime,
    LoggedLine,
)

_FINGERPRINT = "policy-2"


class _FakeFingerprints(PolicyFingerprintReader, PolicyFingerprintWriter):
    """Keeps the fingerprint it is given."""

    def __init__(self, stored_fingerprint: str | None) -> None:
        self.stored_fingerprint = stored_fingerprint

    def read_policy_fingerprint(self) -> str | None:
        return self.stored_fingerprint

    def set_policy_fingerprint(self, fingerprint: str) -> None:
        self.stored_fingerprint = fingerprint


class _Crawl:
    """A ``RunCrawler`` over fakes: two loops that record their node id, then wait for the stop."""

    def __init__(
        self,
        *,
        configured_node_id: str | None = None,
        stored_fingerprint: str | None = _FINGERPRINT,
        download_enabled: bool = False,
    ) -> None:
        self.steps: list[str] = []
        self.event_emitter = FakeEventEmitter()
        self.fingerprints = _FakeFingerprints(stored_fingerprint)
        self.logger = FakeLogger()
        self.reevaluation_gate_logger = FakeLogger()
        self.shutdown = asyncio.Event()
        self._loops_started = 0
        self._both_loops_started = asyncio.Event()
        self.run_crawler = RunCrawler(
            configured_node_id=configured_node_id,
            node_id_reader=FakeNodeIdStore(stored_node_id="stored-node"),
            node_id_writer=FakeNodeIdStore(stored_node_id=None),
            node_id_generator=FakeNodeIdGenerator("new-node"),
            wall_clock=FakeTime().wall,
            event_emitter=self.event_emitter,
            policy_fingerprint=_FINGERPRINT,
            policy_fingerprint_reader=self.fingerprints,
            policy_fingerprint_writer=self.fingerprints,
            reevaluate=self._reevaluate,
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
            self._loops_started += 1
            if self._loops_started == 2:
                self._both_loops_started.set()
            await asyncio.Event().wait()

        return loop

    async def run_until_both_loops_start_then_stop(self) -> None:
        run = asyncio.create_task(
            self.run_crawler.run(arm_shutdown_bound=lambda: self.steps.append("bound armed"))
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
