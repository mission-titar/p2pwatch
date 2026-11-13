"""One work per (client, channel, keyword), searching again as soon as it may (spec stage 2, D4).

The works share one simulated time, so these tests run on the virtual-time loop.
"""

import json
from datetime import timedelta
from typing import Protocol

import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.application.ports.driven.search_client import SearchClient
from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.application.steps.cataloguer import Cataloguer
from p2pwatch.application.steps.file_judge import FileJudge
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.keyword_search import KeywordSearch
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.search_worker import SEARCH_BUDGET_SECONDS, SearchWorker
from p2pwatch.application.steps.supervisor import SupervisedWork, Supervisor
from p2pwatch.composition.turn_time_limits import AmuleTurnTimeLimits
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword, NodeId
from p2pwatch.domain.matching.engine import MatchingEngine
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from p2pwatch.domain.status_reading import channel_component
from p2pwatch.domain.work_components import keyword_search_component
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_loop_wall_clock import FakeLoopWallClock
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_timed_search_client import FakeTimedSearchClient
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.fakes.composition.fake_state_owner import FakeStateOwner
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes
from tests.support.virtual_time import EPOCH, MONOTONIC_EPOCH, VirtualLoop

_NODE_ID = NodeId("n1")
_HOUR = 3600.0
_DAY = timedelta(days=1)
_POLICY = BackoffPolicy(
    base_seconds=60.0,
    cap_seconds=600.0,
    factor=2.0,
    jitter_ratio=0.0,
)


class _TimeLimitOf(Protocol):
    def __call__(self, keyword: Keyword, /, *, channel: Channel) -> timedelta: ...


class _Searches:
    """The works' dependencies, with one client named ``amuled``, run on ``loop``."""

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

    def works(
        self,
        client: SearchClient,
        *,
        keywords: list[str],
        health_recorder: HealthRecorder,
        time_limit_of: _TimeLimitOf = lambda _keyword, *, channel: _DAY,
    ) -> list[SupervisedWork]:
        """One work per channel and keyword, in that order, as the composition enumerates them."""
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
        backoff_saver = BackoffSaver(
            backoff=self.backoff, backoff_state_writer=self.state, logger=FakeLogger()
        )
        channel_components = {
            channel: channel_component(client_name=worker.client_name, channel=channel)
            for channel in worker.channels
        }
        return [
            SupervisedWork(
                work=KeywordSearch(
                    keyword=Keyword(keyword),
                    channel=channel,
                    search_worker=worker,
                    backoff_saver=backoff_saver,
                    monotonic_clock=self.monotonic_clock,
                    health_recorder=health_recorder,
                    channel_component=channel_components[channel],
                ),
                time_limit=time_limit_of(Keyword(keyword), channel=channel),
                feeds=(
                    keyword_search_component(
                        keyword=Keyword(keyword), client_name=worker.client_name, channel=channel
                    ),
                    channel_components[channel],
                ),
            )
            for channel in worker.channels
            for keyword in keywords
        ]

    def run_for(
        self,
        seconds: float,
        *,
        client: SearchClient,
        keywords: list[str],
        time_limit_of: _TimeLimitOf = lambda _keyword, *, channel: _DAY,
        logger: FakeLogger | None = None,
        health_logger: FakeLogger | None = None,
        restarting: bool = False,
    ) -> FakeStateOwner:
        """Runs the works for ``seconds``; ``restarting``, one owner owns their components, each
        of its restarts adding the same works again. Returns that owner."""
        run_state = FakeRunStateStore()
        self.loop.call_later(seconds, run_state.set_shutdown_requested)

        async def restart_policy(transition: HealthTransition) -> None:
            await policy(transition)

        health_recorder = HealthRecorder(
            logger=health_logger or FakeLogger(), subscribers=(restart_policy,)
        )
        works = self.works(
            client, keywords=keywords, health_recorder=health_recorder, time_limit_of=time_limit_of
        )

        def add_works(_state: object) -> None:
            for supervised in works:
                supervisor.add(supervised)

        owner = FakeStateOwner(add_works=add_works)
        components = {c for supervised in works for c in supervised.feeds} if restarting else ()
        policy = RestartPolicy(owners=dict.fromkeys(components, owner), logger=FakeLogger())
        supervisor = Supervisor(
            run_state_reader=run_state,
            monotonic_clock=self.monotonic_clock,
            health_recorder=health_recorder,
            restart_policy=policy,
            logger=logger or FakeLogger(),
        )
        self.loop.run_until_complete(supervisor.supervise(works, arm_shutdown_bound=lambda: None))
        return owner


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


def test_each_channel_and_keyword_searches_in_its_own_work(searches: _Searches) -> None:
    # A channel named `x` needs no code: the works never test a channel's name.
    client = FakeTimedSearchClient({Channel("x"): 30.0, Channel("y"): 30.0})
    searches.run_for(100.0, client=client, keywords=["keroro", "titar"])
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


def test_a_bug_on_one_keywords_searches_leaves_the_other_keywords_searching(
    searches: _Searches,
) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, broken_keywords=frozenset({Keyword("keroro")})
    )
    health_logger = FakeLogger()
    searches.run_for(
        130.0, client=client, keywords=["keroro", "titar"], health_logger=health_logger
    )
    starts = {
        name: [start for start, keyword, _ in client.searches if keyword == name]
        for name in ("keroro", "titar")
    }
    # The broken keyword's searches one floor apart, the other's at their own pace.
    assert starts == {"keroro": [0.0, 60.0, 120.0], "titar": [0.0, 30.0, 60.0, 90.0, 120.0]}
    assert searches.backoff.snapshot() == {}  # a bug never touches the backoff
    # The channel degraded at its second bug among ten, the healthy keyword's turns among them.
    assert _unwell(health_logger) == [
        "channel amuled kad, bugs: healthy to degraded",
        "search 'keroro' amuled kad, bugs: unknown to failing",
    ]


def test_a_bug_on_one_keyword_s_searches_restarts_its_client_three_times_at_most(
    searches: _Searches,
) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, broken_keywords=frozenset({Keyword("keroro")})
    )

    owner = searches.run_for(_HOUR, client=client, keywords=["keroro", "titar"], restarting=True)

    # Its third bug restarts the client, each rebuilt search taking three bugs to fail again.
    assert owner.attempts == [120.0, 240.0, 360.0]
    titar = [start for start, keyword, _ in client.searches if keyword == "titar"]
    assert titar[-1] >= _HOUR - 30.0  # the other keyword searching to the end


def test_a_bug_on_every_kad_search_leaves_the_ed2k_searches_going_on(searches: _Searches) -> None:
    client = FakeTimedSearchClient(
        {Channel("ed2k"): 30.0, Channel("kad"): 30.0}, broken_channels=frozenset({Channel("kad")})
    )
    health_logger = FakeLogger()
    searches.run_for(
        130.0, client=client, keywords=["keroro", "titar"], health_logger=health_logger
    )
    starts = {
        name: sorted(start for start, _, channel in client.searches if channel == name)
        for name in ("ed2k", "kad")
    }
    assert starts == {
        "ed2k": [0.0, 0.0, 30.0, 30.0, 60.0, 60.0, 90.0, 90.0, 120.0, 120.0],
        "kad": [0.0, 0.0, 60.0, 60.0, 120.0, 120.0],
    }
    assert sorted(_unwell(health_logger)) == [
        "channel amuled kad, bugs: unknown to failing",
        "search 'keroro' amuled kad, bugs: unknown to failing",
        "search 'titar' amuled kad, bugs: unknown to failing",
    ]


def _unwell(health_logger: FakeLogger) -> list[str]:
    """The health changes into degraded or failing, as the recorder logs them."""
    return [line.message for line in health_logger.lines if line.level == "warning"]


def _health_lines(health_logger: FakeLogger, *, of: str) -> list[str]:
    return [line.message for line in health_logger.lines if line.message.startswith(of)]


def test_three_refused_searches_in_a_row_fail_their_channel_s_searches(searches: _Searches) -> None:
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, search_failures=[SearchFailedError("refused")] * 3
    )
    health_logger = FakeLogger()
    searches.run_for(200.0, client=client, keywords=["keroro"], health_logger=health_logger)
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 180.0]
    # A refused search is a declared outcome: no bug, the turns' conditions healthy.
    assert _unwell(health_logger) == ["channel amuled kad, searches failed: unknown to failing"]


def test_searches_answered_keep_their_channel_s_searches_healthy(searches: _Searches) -> None:
    health_logger = FakeLogger()
    searches.run_for(
        100.0,
        client=FakeTimedSearchClient({Channel("kad"): 30.0}),
        keywords=["keroro"],
        health_logger=health_logger,
    )
    assert _health_lines(health_logger, of="channel amuled kad, searches failed") == [
        "channel amuled kad, searches failed: unknown to healthy"
    ]


def test_a_bug_between_refused_searches_records_nothing_on_their_channel_s_searches(
    searches: _Searches,
) -> None:
    refused = SearchFailedError("refused")
    client = FakeTimedSearchClient(
        {Channel("kad"): 30.0}, search_failures=[refused, refused, RuntimeError("bug"), refused]
    )
    health_logger = FakeLogger()
    searches.run_for(250.0, client=client, keywords=["keroro"], health_logger=health_logger)
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 180.0, 240.0]
    assert _health_lines(health_logger, of="channel amuled kad, searches failed") == [
        "channel amuled kad, searches failed: unknown to failing"
    ]


def test_an_unreachable_client_is_no_refused_search(searches: _Searches) -> None:
    client = FakeTimedSearchClient({Channel("kad"): 30.0}, search_failures=[make_unreachable()] * 3)
    health_logger = FakeLogger()
    searches.run_for(200.0, client=client, keywords=["keroro"], health_logger=health_logger)
    assert _health_lines(health_logger, of="channel amuled kad, searches failed") == [
        "channel amuled kad, searches failed: unknown to healthy"
    ]


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
    # The first search fails; the other channel's work meets the backoff it set.
    assert [start for start, *_ in client.searches] == [0.0, 60.0, 60.0, 90.0, 90.0]


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


def test_a_work_woken_from_its_wait_waits_again_for_a_backoff_set_meanwhile(
    searches: _Searches,
) -> None:
    client = FakeTimedSearchClient(
        {Channel("ed2k"): 30.0, Channel("kad"): 30.0},
        search_failures=[make_unreachable(), make_unreachable()],
    )
    searches.run_for(200.0, client=client, keywords=["keroro"])
    # Kad's search at 60 s fails again: the eD2k work, woken at 60 s too, waits for its 120 s.
    assert [(start, channel) for start, _, channel in client.searches] == [
        (0.0, "ed2k"),
        (60.0, "kad"),
        (180.0, "ed2k"),
        (180.0, "kad"),
    ]


def test_a_backoff_the_previous_run_saved_delays_the_first_search(searches: _Searches) -> None:
    key = BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad"))
    started_20_s_before = EPOCH - timedelta(seconds=20)
    searches.state.set_backoff_states(
        {key: BackoffState(attempts=1, started_at=started_20_s_before, delay=timedelta(seconds=60))}
    )
    searches.backoff.resume_waits()
    client = FakeTimedSearchClient({Channel("kad"): 30.0})
    searches.run_for(100.0, client=client, keywords=["keroro"])
    assert [start for start, *_ in client.searches] == [40.0, 70.0]


def test_the_supervisor_names_the_work_after_its_keyword_client_and_channel(
    searches: _Searches,
) -> None:
    [work] = searches.works(
        FakeTimedSearchClient({Channel("kad"): 30.0}),
        keywords=["keroro"],
        health_recorder=HealthRecorder(logger=FakeLogger(), subscribers=()),
    )
    assert str(work.work) == work.feeds[0].name == "search 'keroro' amuled kad"


def test_ten_keywords_queued_on_the_clients_ed2k_lock_stay_within_their_time_limits(
    searches: _Searches,
) -> None:
    # Each search held for its budget; requests of 10 s at most, so the limit is short enough
    # that one counting no queue would cut the last keywords' turns.
    keywords = [f"keroro {number:02}" for number in range(1, 11)]
    request_bound = timedelta(seconds=10)
    api = FakeAmuleApi(monotonic_clock=searches.monotonic_clock, progress={"state": "running"})
    store = FakeSearchStartStore()
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
        search_start_writer=store,
        search_start_reader=store,
        transport_factory=api.transport,
    )
    limits = AmuleTurnTimeLimits(
        request_bound=request_bound,
        search_budget=timedelta(seconds=SEARCH_BUDGET_SECONDS),
        notification_timeout=timedelta(seconds=5),
        keywords=tuple(Keyword(keyword) for keyword in keywords),
    )
    logger = FakeLogger()

    searches.run_for(
        3000.0, client=client, keywords=keywords, time_limit_of=limits.of_search, logger=logger
    )
    searches.loop.run_until_complete(client.close())

    ed2k_starts = [query for _, query in _starts(api, search_type="global")]
    assert sorted(set(ed2k_starts)) == keywords  # every keyword through the queue
    assert len(ed2k_starts) >= 2 * len(keywords)
    assert logger.lines == []  # no turn past its limit, no bug


def _starts(api: FakeAmuleApi, *, search_type: str) -> list[tuple[float, str]]:
    """Every ``POST /search`` of one type: when, and for which query."""
    return [
        ((moment - MONOTONIC_EPOCH).total_seconds(), json.loads(request.content)["query"])
        for moment, request in api.calls
        if request.url.path == "/api/v1/search"
        and json.loads(request.content)["type"] == search_type
    ]
