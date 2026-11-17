"""One search per client, channel and keyword, each searching again as soon as it may.

The searches share one simulated time, so these tests run on the virtual-time loop.
"""

import asyncio
import json
from contextlib import suppress
from datetime import timedelta
from typing import Any

import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.keyword_search import SearchTimeLimitOf, keyword_searches
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.search_worker import SEARCH_BUDGET_SECONDS, SearchWorker
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.composition.work_time_limits import AmuleWorkTimeLimits
from p2pwatch.domain.client_errors import ClientAuthError, SearchFailedError
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from p2pwatch.domain.status_reading import channel_component
from p2pwatch.domain.work_components import keyword_search_component
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
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_timed_search_client import FakeTimedSearchClient
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.virtual_time import EPOCH, VirtualLoop

_NODE_ID = NodeId("n1")
_HOUR = 3600.0
# Longer than any of these tests: a turn is cut only where a test sets a shorter limit.
_DAY = timedelta(days=1)
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
        self.supervisor_logger = FakeLogger()
        self.health_logger = FakeLogger()
        self.node_health = NodeHealth(logger=self.health_logger, subscribers=())

    def works(
        self,
        client: Any,
        *,
        keywords: list[str],
        time_limit_of: SearchTimeLimitOf = lambda _keyword, *, channel: _DAY,
    ) -> list[SupervisedWork]:
        """Every search the node would list for ``keywords``, over one client named ``amuled``."""
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
        return keyword_searches(
            search_workers=[worker],
            keywords=keywords,
            backoff_saver=BackoffSaver(
                backoff=self.backoff, backoff_state_writer=self.state, logger=FakeLogger()
            ),
            monotonic_clock=self.monotonic_clock,
            time_limit_of=time_limit_of,
            search_component_of=lambda keyword, *, channel: keyword_search_component(
                keyword=keyword, client_name=worker.client_name, channel=channel
            ),
            node_health=self.node_health,
            channel_components=[
                channel_component(client_name=worker.client_name, channel=channel)
                for channel in worker.channels
            ],
        )

    async def searching(
        self,
        client: Any,
        *,
        keywords: list[str],
        time_limit_of: SearchTimeLimitOf = lambda _keyword, *, channel: _DAY,
    ) -> None:
        """Runs every search the node would list for ``keywords`` under the supervisor, until the
        shutdown is requested."""
        supervisor = Supervisor(
            run_state_reader=self.run_state,
            monotonic_clock=self.monotonic_clock,
            node_health=self.node_health,
            logger=self.supervisor_logger,
        )
        await supervisor.supervise(
            self.works(client, keywords=keywords, time_limit_of=time_limit_of),
            arm_shutdown_bound=lambda: None,
        )

    def run_for(
        self,
        seconds: float,
        *,
        client: Any,
        keywords: list[str],
        time_limit_of: SearchTimeLimitOf = lambda _keyword, *, channel: _DAY,
    ) -> None:
        self.loop.call_later(seconds, self.run_state.set_shutdown_requested)
        self.loop.run_until_complete(
            self.searching(client, keywords=keywords, time_limit_of=time_limit_of)
        )


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


def _bugs_changes(searches: _Searches, *, level: str) -> list[str]:
    """The messages logged at ``level`` of each change of health under the bugs rule."""
    return [
        line.message
        for line in searches.health_logger.lines
        if line.level == level and ", bugs: " in line.message
    ]


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


def test_a_bug_on_every_kad_search_leaves_the_ed2k_searches_going_on(searches: _Searches) -> None:
    client = FakeTimedSearchClient(
        {Channel("ed2k"): 30.0, Channel("kad"): 30.0}, broken_channels=frozenset({Channel("kad")})
    )

    searches.run_for(100.0, client=client, keywords=["keroro", "titar"])

    starts = {
        channel: sorted(
            start for start, _, searched_on in client.searches if searched_on == channel
        )
        for channel in ("ed2k", "kad")
    }
    # Each Kad search meets its bug at 30 s, and its next turn waits 60 s.
    assert starts == {
        "ed2k": [0.0, 0.0, 30.0, 30.0, 60.0, 60.0, 90.0, 90.0],
        "kad": [0.0, 0.0, 90.0, 90.0],
    }


def test_a_bug_on_one_keywords_searches_leaves_the_other_keyword_searching(
    searches: _Searches,
) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, broken_keywords=frozenset({Keyword("keroro")})
    )

    searches.run_for(100.0, client=client, keywords=["keroro", "titar"])

    starts = {
        keyword: [start for start, searched, _ in client.searches if searched == keyword]
        for keyword in ("keroro", "titar")
    }
    assert starts == {"keroro": [0.0, 90.0], "titar": [0.0, 30.0, 60.0, 90.0]}
    assert [line.message for line in searches.supervisor_logger.lines] == [
        "bug in search 'keroro' amuled kad"
    ]
    assert searches.backoff.snapshot() == {}  # a bug never backs its channel off


def test_a_bug_on_every_kad_search_fails_kad_and_its_searches_and_nothing_of_ed2k(
    searches: _Searches,
) -> None:
    client = FakeTimedSearchClient(
        {Channel("ed2k"): 30.0, Channel("kad"): 30.0}, broken_channels=frozenset({Channel("kad")})
    )

    # Each Kad search meets its bug at 30 s, 120 s and 210 s.
    searches.run_for(215.0, client=client, keywords=["keroro", "titar"])

    failing = _bugs_changes(searches, level="warning")
    healthy = _bugs_changes(searches, level="info")
    # Kad meets the bugs of both its searches: its third comes at 120 s.
    assert failing == [
        "channel amuled kad, bugs: unknown to failing",
        "search 'keroro' amuled kad, bugs: unknown to failing",
        "search 'titar' amuled kad, bugs: unknown to failing",
    ]
    assert sorted(healthy) == [
        "channel amuled ed2k, bugs: unknown to healthy",
        "search 'keroro' amuled ed2k, bugs: unknown to healthy",
        "search 'titar' amuled ed2k, bugs: unknown to healthy",
    ]


def test_a_bug_on_one_keywords_searches_fails_that_search_alone(searches: _Searches) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, broken_keywords=frozenset({Keyword("keroro")})
    )

    # The broken keyword meets its bug at 30 s, 120 s and 210 s.
    searches.run_for(215.0, client=client, keywords=["keroro", "titar"])

    failing = _bugs_changes(searches, level="warning")
    healthy = _bugs_changes(searches, level="info")
    assert failing == ["search 'keroro' amuled kad, bugs: unknown to failing"]
    # The other keyword's turns come between its bugs: Kad never meets three in a row.
    assert sorted(healthy) == [
        "channel amuled kad, bugs: unknown to healthy",
        "search 'titar' amuled kad, bugs: unknown to healthy",
    ]


def _searches_failed_lines(searches: _Searches) -> list[LoggedLine]:
    """The log lines of each change of the channels' health under "searches failed"."""
    return [line for line in searches.health_logger.lines if ", searches failed: " in line.message]


def test_three_refused_searches_in_a_row_fail_the_channel_and_nine_that_ran_heal_it(
    searches: _Searches,
) -> None:
    refused: list[Exception] = [SearchFailedError("refused")] * 3
    client = FakeTimedSearchClient({Channel("kad"): 30.0}, search_failures=refused)

    # Refused at 0 s, 60 s and 180 s, each after its backoff; the ninth that ran starts at 660 s.
    searches.run_for(700.0, client=client, keywords=["keroro"])

    assert _searches_failed_lines(searches) == [
        LoggedLine(
            level="warning", message="channel amuled kad, searches failed: unknown to failing"
        ),
        LoggedLine(level="info", message="channel amuled kad, searches failed: failing to healthy"),
    ]


def test_an_unreachable_client_after_three_refused_searches_leaves_the_channel_failing(
    searches: _Searches,
) -> None:
    refused: list[Exception] = [SearchFailedError("refused")] * 3
    unreachable: list[Exception] = [make_unreachable()] * 9
    client = FakeTimedSearchClient({Channel("kad"): 30.0}, search_failures=refused + unreachable)

    # The ninth unreachable turn starts at 3720 s, after the client's backoff of 600 s.
    searches.run_for(4000.0, client=client, keywords=["keroro"])

    assert len(client.searches) == 12
    # aMule down tells nothing of the network: the channel is neither healed nor failed by it.
    assert _searches_failed_lines(searches) == [
        LoggedLine(
            level="warning", message="channel amuled kad, searches failed: unknown to failing"
        )
    ]


@pytest.mark.parametrize(
    "error",
    [
        ClientAuthError("amuleapi refused the admin password"),
        RuntimeError("an answer the mapper cannot read"),
    ],
    ids=["a-refused-password", "a-bug"],
)
def test_a_refused_password_or_a_bug_tells_nothing_of_the_channel_s_searches(
    searches: _Searches, *, error: Exception
) -> None:
    client = FakeTimedSearchClient({Channel("kad"): 30.0}, search_failures=[error] * 3)
    [search] = searches.works(client, keywords=["keroro"])

    for _ in range(3):
        with pytest.raises(type(error)):
            searches.loop.run_until_complete(search.work.run_once())

    # Three checks would have changed the rule's state, either way.
    assert searches.health_logger.lines == []


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


@pytest.mark.parametrize(
    ("error", "line", "backed_off"),
    [
        (
            SearchFailedError("refused"),
            "search 'keroro' amuled kad: refused",
            BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad")),
        ),
        (
            make_unreachable(),
            "search 'keroro' amuled kad: down",
            BackoffKey(client_name=ClientName("amuled"), channel=None),
        ),
    ],
    ids=["a-refused-search", "an-unreachable-client"],
)
def test_a_failed_search_fails_its_turn_as_an_expected_error_once_its_backoff_is_saved(
    searches: _Searches, *, error: Exception, line: str, backed_off: BackoffKey
) -> None:
    client = FakeTimedSearchClient({Channel("kad"): 30.0}, search_failures=[error])

    searches.run_for(50.0, client=client, keywords=["keroro"])

    assert searches.supervisor_logger.lines == [LoggedLine(level="warning", message=line)]
    assert [set(saved) for saved in searches.state.saved] == [{backed_off}]


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


def test_each_search_is_named_after_its_keyword_client_and_channel(searches: _Searches) -> None:
    [search] = searches.works(FakeTimedSearchClient({Channel("kad"): 30.0}), keywords=["keroro"])
    assert str(search.work) == "search 'keroro' amuled kad"


def test_ten_ed2k_keywords_queued_on_the_client_each_search_within_its_time_limit(
    searches: _Searches,
) -> None:
    # Each search held for its whole budget; requests bounded at 10 s, so that a limit counting
    # no search ahead on the client would cut the last keywords' searches.
    keywords = [f"keroro {number:02}" for number in range(1, 11)]
    request_bound = timedelta(seconds=10)
    api = FakeAmuleApi(monotonic_clock=searches.monotonic_clock, progress={"state": "running"})
    search_start_store = FakeSearchStartStore()
    client = AmuleApiClient(
        "amuled.test",
        client_name=ClientName("amuled"),
        port=4711,
        password=PASSWORD,
        timeout_seconds=10.0,
        request_bound_seconds=request_bound.total_seconds(),
        page_size=500,
        progress_poll_interval=timedelta(seconds=5),
        monotonic_clock=searches.monotonic_clock,
        wall_clock=searches.wall_clock,
        search_start_writer=search_start_store,
        search_start_reader=search_start_store,
        transport_factory=api.transport,
    )
    time_limits = AmuleWorkTimeLimits(
        request_bound=request_bound,
        search_budget=timedelta(seconds=SEARCH_BUDGET_SECONDS),
        notification_timeout=timedelta(seconds=5),
        keywords=[Keyword(keyword) for keyword in keywords],
    )

    searches.run_for(3000.0, client=client, keywords=keywords, time_limit_of=time_limits.of_search)
    searches.loop.run_until_complete(client.close())

    ed2k_starts = [
        json.loads(request.content)["query"]
        for _, request in api.calls
        if request.method == "POST"
        and request.url.path == "/api/v1/search"
        and json.loads(request.content)["type"] == "global"
    ]
    # Each keyword in its turn through the queue, at least twice, and no turn cut nor other bug.
    assert len(ed2k_starts) >= 2 * len(keywords)
    assert ed2k_starts == (keywords * 3)[: len(ed2k_starts)]
    assert searches.supervisor_logger.lines == []
