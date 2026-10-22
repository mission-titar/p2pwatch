"""One task per (client, channel, keyword), searching again as soon as it may (spec stage 2, D4).

The tasks share one simulated time, so these tests run on the virtual-time loop.
"""

import asyncio
import sqlite3
from collections.abc import Coroutine
from contextlib import suppress
from datetime import timedelta
from typing import Any

import pytest

from catalog_matching.domain.engine import MatchingEngine
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.steps.search_tasks import SearchTaskRunner
from p2pwatch.application.steps.search_worker import (
    BackoffPolicy,
    BackoffRegistry,
    SearchWorker,
    WorkerDeps,
)
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_loop_wall_clock import FakeLoopWallClock
from tests.fakes.adapters.driven.fake_never_suspending_search_client import (
    FakeNeverSuspendingSearchClient,
)
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_timed_search_client import FakeTimedSearchClient
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.catalog_rows import observation_node_ids
from tests.support.virtual_time import EPOCH, run_virtual

_NODE = "n1"
_HOUR = 3600.0
_POLICY = BackoffPolicy(
    base_seconds=60.0,
    cap_seconds=600.0,
    factor=2.0,
    jitter_ratio=0.0,
)


class _Tasks:
    """The tasks' dependencies, with one client named ``amuled``."""

    def __init__(self, deps: WorkerDeps, state: FakeBackoffStateStore) -> None:
        self.deps = deps
        self.state = state
        self.resumed = asyncio.Event()
        self.resumed.set()
        self.logger = FakeLogger()

    def searching(self, client: Any, keywords: list[str]) -> Coroutine[Any, Any, None]:
        return SearchTaskRunner(
            workers=[SearchWorker("amuled", client, self.deps)],
            keywords=keywords,
            resumed=self.resumed,
            backoff=self.deps.backoff,
            backoff_state_writer=self.state,
            monotonic_clock=FakeLoopMonotonicClock(),
            logger=self.logger,
        ).run(_NODE)

    def run_for(
        self, seconds: float, client: Any, keywords: list[str], *beside: Coroutine[Any, Any, None]
    ) -> None:
        async def bounded() -> None:
            with suppress(TimeoutError):
                async with asyncio.timeout(seconds):
                    await asyncio.gather(self.searching(client, keywords), *beside)

        run_virtual(bounded())


@pytest.fixture
def tasks(
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
) -> _Tasks:
    wall_clock = FakeLoopWallClock()
    backoff = BackoffRegistry(_POLICY, wall_clock, FakeLoopMonotonicClock(), FakeJitterGenerator())
    waker, event_emitter = FakeWaker(), FakeEventEmitter()
    deps = WorkerDeps(
        observation_writer=observation_store,
        observation_reader=observation_store,
        decision_writer=decision_store,
        decision_reader=decision_store,
        engine=engine,
        waker=waker,
        backoff=backoff,
        event_emitter=event_emitter,
        wall_clock=wall_clock,
        logger=FakeLogger(),
        observation_logger=FakeLogger(),
    )
    return _Tasks(deps, FakeBackoffStateStore())


def test_each_channel_and_keyword_searches_in_its_own_task(tasks: _Tasks) -> None:
    # A channel named `x` needs no code: the tasks never test a channel's name.
    client = FakeTimedSearchClient({"x": 30.0, "y": 30.0})
    tasks.run_for(100.0, client, ["keroro", "titar", "keroro", ""])
    assert sorted(client.searches) == sorted(
        (start, keyword, channel)
        for start in (0.0, 30.0, 60.0, 90.0)
        for keyword in ("keroro", "titar")
        for channel in ("x", "y")
    )


def test_a_task_records_its_observations_under_the_node_id_the_tasks_run_with(
    tasks: _Tasks, catalog_connection: sqlite3.Connection
) -> None:
    reported_file = ReportedFile(FileKey(Network.ED2K, "a" * 32), "keroro.avi", 1, 1, "keroro")
    tasks.run_for(
        40.0, FakeTimedSearchClient({"x": 30.0}, reported_files=(reported_file,)), ["keroro"]
    )
    assert observation_node_ids(catalog_connection) == {_NODE}


def test_channels_do_not_wait_for_each_other(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient({"ed2k": 6.0, "kad": 60.0})
    tasks.run_for(_HOUR, client, ["keroro"])
    counts = {name: sum(1 for *_, c in client.searches if c == name) for name in client.channels()}
    assert counts["ed2k"] >= 5 * counts["kad"]


def test_a_paused_task_waits_before_its_next_search_and_finishes_the_one_in_flight(
    tasks: _Tasks,
) -> None:
    client = FakeTimedSearchClient({"kad": 30.0})

    async def pause_then_resume() -> None:
        await asyncio.sleep(10.0)
        tasks.resumed.clear()
        await asyncio.sleep(990.0)
        tasks.resumed.set()

    tasks.run_for(1040.0, client, ["keroro"], pause_then_resume())
    assert [start for start, *_ in client.searches] == [0.0, 1000.0, 1030.0]


def test_a_failed_channel_sleeps_until_its_backoff_ends(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient({"kad": 30.0}, search_failures=[SearchFailedError("refused")])
    tasks.run_for(100.0, client, ["keroro"])
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 90.0]


def test_an_unreachable_client_sleeps_until_its_backoff_ends(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient(
        {"ed2k": 30.0, "kad": 30.0}, search_failures=[make_unreachable()]
    )
    tasks.run_for(100.0, client, ["keroro"])
    # The first search fails; the other channel's task meets the backoff it set.
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 60.0, 90.0, 90.0]


def test_the_backoff_is_saved_at_each_change(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient({"kad": 30.0}, search_failures=[SearchFailedError("refused")])
    tasks.run_for(_HOUR, client, ["keroro"])
    assert [set(saved) for saved in tasks.state.saved] == [{BackoffKey("amuled", "kad")}, set()]
    assert tasks.state.read_backoff_states() == {}


def test_a_failed_save_is_logged_and_retried_after_the_next_search(tasks: _Tasks) -> None:
    tasks.state.failures = 1
    refused: list[Exception] = [SearchFailedError("refused"), SearchFailedError("refused")]
    client = FakeTimedSearchClient({"kad": 30.0}, search_failures=refused)
    tasks.run_for(100.0, client, ["keroro"])
    assert tasks.logger.lines == [
        LoggedLine("error", "backoff not saved (database is locked): retried after the next search")
    ]
    second_failure = BackoffState(2, EPOCH + timedelta(seconds=60), timedelta(seconds=120))
    assert tasks.state.saved == [{BackoffKey("amuled", "kad"): second_failure}]


def test_a_search_that_never_suspends_does_not_starve_the_loop(tasks: _Tasks) -> None:
    client = FakeNeverSuspendingSearchClient()

    async def main() -> None:
        searching = asyncio.ensure_future(tasks.searching(client, ["keroro"]))
        while not searching.done():
            client.ticks += 1
            if client.calls >= 100:
                searching.cancel()
            await asyncio.sleep(0)
        with suppress(asyncio.CancelledError):
            await searching

    run_virtual(main())
    assert client.calls >= 100
