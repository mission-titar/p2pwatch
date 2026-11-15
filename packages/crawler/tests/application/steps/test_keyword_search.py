"""One search per client, channel and keyword, each searching again as soon as it may.

The searches share one simulated time, so these tests run on the virtual-time loop.
"""

import asyncio
from contextlib import suppress
from datetime import timedelta
from typing import Any

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.keyword_search import keyword_searches
from p2pwatch.application.steps.search_worker import SearchWorker
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
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
from tests.support.virtual_time import EPOCH, VirtualLoop

_NODE_ID = NodeId("n1")
_HOUR = 3600.0
_POLICY = BackoffPolicy(
    base_seconds=60.0,
    cap_seconds=600.0,
    factor=2.0,
    jitter_ratio=0.0,
)


class _Searches:
    """The searches' dependencies, with one client named ``amuled``, run on ``loop``."""

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

    async def searching(self, client: Any, *, keywords: list[str]) -> None:
        """Runs every search the node would list for ``keywords`` under the supervisor, until the
        shutdown is requested."""
        dispatcher = ObservabilityOverFakes().dispatcher
        file_judge = FileJudge(
            observation_reader=self.observation_store,
            decision_writer=self.decision_store,
            decision_reader=self.decision_store,
            engine=self.engine,
            waker=FakeWaker(),
            observability_dispatcher=dispatcher,
            wall_clock=self.wall_clock,
            node_id=_NODE_ID,
        )
        cataloguer = Cataloguer(
            observation_writer=self.observation_store,
            file_judge=file_judge,
            observability_dispatcher=dispatcher,
            wall_clock=self.wall_clock,
            node_id=_NODE_ID,
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
        searches = keyword_searches(
            search_workers=[worker],
            keywords=keywords,
            backoff_saver=BackoffSaver(
                backoff=self.backoff, backoff_state_writer=self.state, logger=FakeLogger()
            ),
            monotonic_clock=self.monotonic_clock,
        )
        await Supervisor(run_state_reader=self.run_state).supervise(
            searches, arm_shutdown_bound=lambda: None
        )

    def run_for(
        self,
        seconds: float,
        *,
        client: Any,
        keywords: list[str],
    ) -> None:
        self.loop.call_later(seconds, self.run_state.set_shutdown_requested)
        self.loop.run_until_complete(self.searching(client, keywords=keywords))


@pytest.fixture
def searches(
    *,
    observation_store: SqliteObservationStore,
    decision_store: SqliteDecisionStore,
    engine: MatchingEngine,
    virtual_loop: VirtualLoop,
) -> _Searches:
    return _Searches(
        observation_store, decision_store=decision_store, engine=engine, loop=virtual_loop
    )


def test_each_channel_and_keyword_searches_in_its_own_task(searches: _Searches) -> None:
    # A channel named `x` needs no code: the searches never test a channel's name.
    client = FakeTimedSearchClient({Channel("x"): 30.0, Channel("y"): 30.0})
    searches.run_for(100.0, client=client, keywords=["keroro", "titar", "keroro", ""])
    assert sorted(client.searches) == sorted(
        (start, keyword, channel)
        for start in (0.0, 30.0, 60.0, 90.0)
        for keyword in ("keroro", "titar")
        for channel in ("x", "y")
    )


def test_channels_do_not_wait_for_each_other(searches: _Searches) -> None:
    client = FakeTimedSearchClient({Channel("ed2k"): 6.0, Channel("kad"): 60.0})
    searches.run_for(_HOUR, client=client, keywords=["keroro"])
    counts = {name: sum(1 for *_, c in client.searches if c == name) for name in client.channels()}
    assert counts[Channel("ed2k")] >= 5 * counts[Channel("kad")]


def test_a_failed_channel_sleeps_until_its_backoff_ends(searches: _Searches) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, search_failures=[SearchFailedError("refused")]
    )
    searches.run_for(100.0, client=client, keywords=["keroro"])
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 90.0]


def test_an_unreachable_client_sleeps_until_its_backoff_ends(searches: _Searches) -> None:
    client = FakeTimedSearchClient(
        {Channel("ed2k"): 30.0, Channel("kad"): 30.0}, search_failures=[make_unreachable()]
    )
    searches.run_for(100.0, client=client, keywords=["keroro"])
    # The first search fails; the other channel's search meets the backoff it set.
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 60.0, 90.0, 90.0]


def test_a_search_woken_from_its_wait_waits_again_for_a_backoff_set_meanwhile(
    searches: _Searches,
) -> None:
    client = FakeTimedSearchClient(
        {Channel("ed2k"): 30.0, Channel("kad"): 30.0},
        search_failures=[make_unreachable(), make_unreachable()],
    )
    searches.run_for(200.0, client=client, keywords=["keroro"])
    # Both wake at 60 s; Kad's search fails again, so eD2k waits the second backoff's 120 s.
    assert [(start, channel) for start, _, channel in client.searches] == [
        (0.0, "ed2k"),
        (60.0, "kad"),
        (180.0, "ed2k"),
        (180.0, "kad"),
    ]


def test_a_backoff_the_previous_run_saved_delays_the_first_search(searches: _Searches) -> None:
    searches.state.set_backoff_states(
        {
            BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad")): BackoffState(
                attempts=1,
                started_at=EPOCH - timedelta(seconds=20),
                delay=timedelta(seconds=60),
            )
        }
    )
    searches.backoff.resume_waits()  # as the lifecycle does at the start
    client = FakeTimedSearchClient({Channel("kad"): 30.0})
    searches.run_for(100.0, client=client, keywords=["keroro"])
    assert [start for start, *_ in client.searches] == [40.0, 70.0]


def test_the_backoff_is_saved_at_each_change(searches: _Searches) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, search_failures=[SearchFailedError("refused")]
    )
    searches.run_for(_HOUR, client=client, keywords=["keroro"])
    assert [set(saved) for saved in searches.state.saved] == [
        {BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad"))},
        set(),
    ]
    assert searches.state.read_backoff_states() == {}


def test_a_search_that_never_suspends_does_not_starve_the_loop(searches: _Searches) -> None:
    client = FakeNeverSuspendingSearchClient()

    async def main() -> None:
        searching = asyncio.ensure_future(searches.searching(client, keywords=["keroro"]))
        while not searching.done():
            client.ticks += 1
            if client.calls >= 100:
                searching.cancel()
            await asyncio.sleep(0)  # noqa: TID251
        with suppress(asyncio.CancelledError):
            await searching

    searches.loop.run_until_complete(main())
    assert client.calls >= 100
