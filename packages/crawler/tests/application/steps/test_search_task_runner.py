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
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.search_task_runner import SearchTaskRunner
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.observation import ReportedFile
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_loop_wall_clock import FakeLoopWallClock
from tests.fakes.adapters.driven.fake_never_suspending_search_client import (
    FakeNeverSuspendingSearchClient,
)
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_timed_search_client import FakeTimedSearchClient
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.catalog_rows import observation_node_ids
from tests.support.virtual_time import EPOCH, VirtualLoop

_NODE_ID = NodeId("n1")
_HOUR = 3600.0
_POLICY = BackoffPolicy(
    base_seconds=60.0,
    cap_seconds=600.0,
    factor=2.0,
    jitter_ratio=0.0,
)


class _Tasks:
    """The tasks' dependencies, with one client named ``amuled``, run on ``loop``."""

    def __init__(
        self,
        observation_store: SqliteObservationStore,
        *,
        decision_store: SqliteDecisionStore,
        engine: MatchingEngine,
        loop: VirtualLoop,
    ) -> None:
        self.loop = loop
        self.observation_store = observation_store
        self.decision_store = decision_store
        self.engine = engine
        self.wall_clock = FakeLoopWallClock(loop)
        self.state = FakeBackoffStateStore()
        self.monotonic_clock = FakeLoopMonotonicClock(loop)
        self.backoff = BackoffRegistry(
            _POLICY,
            wall_clock=self.wall_clock,
            monotonic_clock=self.monotonic_clock,
            jitter_generator=FakeJitterGenerator(),
            backoff_state_reader=self.state,
        )
        self.run_state = FakeRunStateStore()
        self.logger = FakeLogger()

    def searching(self, client: Any, *, keywords: list[str]) -> Coroutine[Any, Any, None]:
        dispatcher = ObservabilityOverFakes().dispatcher
        file_judge = FileJudge(
            observation_reader=self.observation_store,
            decision_writer=self.decision_store,
            decision_reader=self.decision_store,
            engine=self.engine,
            waker=FakeWaker(),
            observability_dispatcher=dispatcher,
            wall_clock=self.wall_clock,
        )
        cataloguer = Cataloguer(
            observation_writer=self.observation_store,
            file_judge=file_judge,
            observability_dispatcher=dispatcher,
            wall_clock=self.wall_clock,
            logger=FakeLogger(),
        )
        worker = SearchWorker(
            client_name=ClientName("amuled"),
            client=client,
            backoff=self.backoff,
            cataloguer=cataloguer,
            observability_dispatcher=dispatcher,
            logger=FakeLogger(),
        )
        return SearchTaskRunner(
            workers=[worker],
            keywords=keywords,
            run_state_reader=self.run_state,
            backoff=self.backoff,
            backoff_state_writer=self.state,
            monotonic_clock=self.monotonic_clock,
            logger=self.logger,
        ).run(_NODE_ID)

    def run_for(
        self,
        seconds: float,
        *,
        client: Any,
        keywords: list[str],
        beside: tuple[Coroutine[Any, Any, None], ...] = (),
    ) -> None:
        async def bounded() -> None:
            with suppress(TimeoutError):
                async with asyncio.timeout(seconds):
                    await asyncio.gather(self.searching(client, keywords=keywords), *beside)

        self.loop.run_until_complete(bounded())


@pytest.fixture
def tasks(
    *,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    virtual_loop: VirtualLoop,
) -> _Tasks:
    return _Tasks(
        observation_store, decision_store=decision_store, engine=engine, loop=virtual_loop
    )


def test_each_channel_and_keyword_searches_in_its_own_task(tasks: _Tasks) -> None:
    # A channel named `x` needs no code: the tasks never test a channel's name.
    client = FakeTimedSearchClient({Channel("x"): 30.0, Channel("y"): 30.0})
    tasks.run_for(100.0, client=client, keywords=["keroro", "titar", "keroro", ""])
    assert sorted(client.searches) == sorted(
        (start, keyword, channel)
        for start in (0.0, 30.0, 60.0, 90.0)
        for keyword in ("keroro", "titar")
        for channel in ("x", "y")
    )


def test_a_task_records_its_observations_under_the_node_id_the_tasks_run_with(
    *, tasks: _Tasks, catalog_connection: sqlite3.Connection
) -> None:
    reported_file = ReportedFile(
        file=FileKey(network=Network.ED2K, native_id="a" * 32),
        filename="keroro.avi",
        size_bytes=1,
        source_count=1,
        keyword=Keyword("keroro"),
    )
    tasks.run_for(
        40.0,
        client=FakeTimedSearchClient({Channel("x"): 30.0}, reported_files=(reported_file,)),
        keywords=["keroro"],
    )
    assert observation_node_ids(catalog_connection) == {_NODE_ID}


def test_channels_do_not_wait_for_each_other(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient({Channel("ed2k"): 6.0, Channel("kad"): 60.0})
    tasks.run_for(_HOUR, client=client, keywords=["keroro"])
    counts = {name: sum(1 for *_, c in client.searches if c == name) for name in client.channels()}
    assert counts[Channel("ed2k")] >= 5 * counts[Channel("kad")]


def test_a_paused_task_waits_before_its_next_search_and_finishes_the_one_in_flight(
    tasks: _Tasks,
) -> None:
    client = FakeTimedSearchClient({Channel("kad"): 30.0})

    async def pause_then_resume() -> None:
        await asyncio.sleep(10.0)  # noqa: TID251
        tasks.run_state.set_paused(True)
        await asyncio.sleep(990.0)  # noqa: TID251
        tasks.run_state.set_paused(False)

    tasks.run_for(1040.0, client=client, keywords=["keroro"], beside=(pause_then_resume(),))
    assert [start for start, *_ in client.searches] == [0.0, 1000.0, 1030.0]


def test_a_failed_channel_sleeps_until_its_backoff_ends(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, search_failures=[SearchFailedError("refused")]
    )
    tasks.run_for(100.0, client=client, keywords=["keroro"])
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 90.0]


def test_an_unreachable_client_sleeps_until_its_backoff_ends(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient(
        {Channel("ed2k"): 30.0, Channel("kad"): 30.0}, search_failures=[make_unreachable()]
    )
    tasks.run_for(100.0, client=client, keywords=["keroro"])
    # The first search fails; the other channel's task meets the backoff it set.
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 60.0, 90.0, 90.0]


def test_the_backoff_is_saved_at_each_change(tasks: _Tasks) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, search_failures=[SearchFailedError("refused")]
    )
    tasks.run_for(_HOUR, client=client, keywords=["keroro"])
    assert [set(saved) for saved in tasks.state.saved] == [
        {BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad"))},
        set(),
    ]
    assert tasks.state.read_backoff_states() == {}


def test_the_backoff_resumed_after_the_tasks_were_built_is_not_saved_again(
    tasks: _Tasks,
) -> None:
    resumed = {
        BackoffKey(client_name=ClientName("amuled"), channel=Channel("ed2k")): BackoffState(
            attempts=1, started_at=EPOCH, delay=timedelta(seconds=60)
        )
    }
    tasks.state.set_backoff_states(resumed)  # the previous run's save

    async def resume_once_built() -> None:
        searching = tasks.searching(
            FakeTimedSearchClient({Channel("kad"): 30.0}), keywords=["keroro"]
        )
        tasks.backoff.resume_waits()
        with suppress(TimeoutError):
            async with asyncio.timeout(100.0):
                await searching

    tasks.loop.run_until_complete(resume_once_built())
    assert tasks.state.saved == [resumed]


def test_a_failed_save_is_logged_and_retried_after_the_next_search(tasks: _Tasks) -> None:
    tasks.state.failures = 1
    refused: list[Exception] = [SearchFailedError("refused"), SearchFailedError("refused")]
    client = FakeTimedSearchClient({Channel("kad"): 30.0}, search_failures=refused)
    tasks.run_for(100.0, client=client, keywords=["keroro"])
    assert tasks.logger.lines == [
        LoggedLine(
            level="error",
            message="backoff not saved (database is locked): retried after the next search",
        )
    ]
    second_failure = BackoffState(
        attempts=2, started_at=EPOCH + timedelta(seconds=60), delay=timedelta(seconds=120)
    )
    assert tasks.state.saved == [
        {BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad")): second_failure}
    ]


def test_a_search_that_never_suspends_does_not_starve_the_loop(tasks: _Tasks) -> None:
    client = FakeNeverSuspendingSearchClient()

    async def main() -> None:
        searching = asyncio.ensure_future(tasks.searching(client, keywords=["keroro"]))
        while not searching.done():
            client.ticks += 1
            if client.calls >= 100:
                searching.cancel()
            await asyncio.sleep(0)  # noqa: TID251
        with suppress(asyncio.CancelledError):
            await searching

    tasks.loop.run_until_complete(main())
    assert client.calls >= 100
