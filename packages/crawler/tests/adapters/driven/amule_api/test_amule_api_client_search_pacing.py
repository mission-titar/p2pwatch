"""``AmuleApiClient.search()`` paces its starts by the rules of eD2k and Kad (spec stage 2, D5).

Concurrent searches need one shared time, so those tests run on an event loop whose clock is
virtual: whenever every task waits, the loop jumps to the next timer instead of sleeping.
"""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.search.answer import SearchAnswer
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi, error
from tests.support.virtual_time import MONOTONIC_EPOCH, VirtualLoop

_HOUR = 3600.0
_BUDGET = 120.0
_ALREADY_SEARCHING = (
    "Unexpected error while attempting Kad search: "
    "Kademlia: Search keyword is already on search list: keroro"
)


def _api(loop: VirtualLoop, **kwargs: Any) -> FakeAmuleApi:
    return FakeAmuleApi(monotonic_clock=FakeLoopMonotonicClock(loop), **kwargs)


async def _connected(api: FakeAmuleApi) -> AmuleApiClient:
    client = AmuleApiClient(
        "amuled.test",
        port=4711,
        password=PASSWORD,
        timeout_seconds=10.0,
        page_size=500,
        progress_poll_interval=timedelta(seconds=5),
        transport_factory=api.transport,
        monotonic_clock=api.monotonic_clock,
    )
    await client.open()
    return client


def _elapsed(moment: MonotonicInstant) -> float:
    return (moment - MONOTONIC_EPOCH).total_seconds()


def _starts(api: FakeAmuleApi, search_type: str) -> list[tuple[float, str]]:
    """Every ``POST /search`` of one type: when, and for which query."""
    starts = []
    for moment, request in api.calls:
        if request.method == "POST" and request.url.path == "/api/v1/search":
            body = json.loads(request.content)
            if body["type"] == search_type:
                starts.append((_elapsed(moment), body["query"]))
    return starts


def _gaps(times: list[float]) -> list[float]:
    return [later - earlier for earlier, later in zip(times, times[1:], strict=False)]


def _polled_until(api: FakeAmuleApi, search_id: int) -> float:
    """When a search's progress was last read, in seconds after its start."""
    started_at = api.searches[search_id][0]
    path = f"/api/v1/search/{search_id}/results"
    return max(
        (moment - started_at).total_seconds()
        for moment, request in api.calls
        if request.url.path == path and request.url.params.get("limit") == "0"
    )


async def _search_for(api: FakeAmuleApi, keywords: list[Keyword], channels: list[Channel]) -> None:
    """One task per (channel, keyword), each searching again as soon as it returns, for an hour."""
    client = await _connected(api)
    loop = asyncio.get_running_loop()

    async def task(keyword: Keyword, channel: Channel) -> None:
        while loop.time() < _HOUR:
            await client.search(keyword, channel=channel, budget_seconds=_BUDGET)
            await asyncio.sleep(0)  # noqa: TID251

    await asyncio.gather(*(task(keyword, channel) for keyword in keywords for channel in channels))
    await client.close()


# ed2k's `keroro` runs past 60 s, so both ed2k rules take turns binding.
_DURATIONS = {"keroro": 90.0, "keroro mission": 30.0, "titar": 30.0}
_TARGETS = {"keroro": "keroro", "keroro mission": "keroro", "titar": "titar"}


def _hour_of_three_keywords(loop: VirtualLoop) -> FakeAmuleApi:
    api = _api(loop, search_seconds=dict(_DURATIONS))
    loop.run_until_complete(
        _search_for(api, [Keyword(text) for text in _DURATIONS], [Channel("ed2k"), Channel("kad")])
    )
    return api


@pytest.mark.parametrize("channel", ["ed2k", "kad"])
@pytest.mark.parametrize("step", [timedelta(hours=-1), timedelta(hours=1)])
@pytest.mark.asyncio
async def test_a_wall_clock_step_leaves_two_starts_a_minute_apart(
    channel: Channel, step: timedelta
) -> None:
    fake_time = FakeTime()
    client = await _connected(FakeAmuleApi(monotonic_clock=fake_time.monotonic))
    await client.search(Keyword("keroro"), channel=channel, budget_seconds=_BUDGET)
    fake_time.step_wall(step)
    await client.search(Keyword("keroro"), channel=channel, budget_seconds=_BUDGET)
    await client.close()

    assert fake_time.sleeps == [timedelta(seconds=60)]


def test_ed2k_starts_are_a_minute_apart_or_more(virtual_loop: VirtualLoop) -> None:
    api = _hour_of_three_keywords(virtual_loop)

    starts = [moment for moment, _ in _starts(api, "global")]
    assert len(starts) > 30
    assert min(_gaps(starts)) >= 60


def test_no_ed2k_start_falls_while_the_previous_search_runs(virtual_loop: VirtualLoop) -> None:
    api = _hour_of_three_keywords(virtual_loop)

    starts = _starts(api, "global")
    for (previous, query), (start, _) in zip(starts, starts[1:], strict=False):
        assert start >= previous + _DURATIONS[query], (previous, query, start)


def test_kad_starts_on_one_target_are_a_minute_apart_whatever_keywords_share_it(
    virtual_loop: VirtualLoop,
) -> None:
    api = _hour_of_three_keywords(virtual_loop)

    starts = _starts(api, "kad")
    for target in ("keroro", "titar"):
        times = [moment for moment, query in starts if _TARGETS[query] == target]
        assert len(times) > 30
        assert min(_gaps(times)) >= 60, target


def test_kad_targets_and_ed2k_start_together(virtual_loop: VirtualLoop) -> None:
    api = _hour_of_three_keywords(virtual_loop)

    assert [moment for moment, _ in _starts(api, "kad")][:2] == [0, 0]
    assert _starts(api, "global")[0][0] == 0


def test_each_search_gets_its_budget_from_its_network_start(virtual_loop: VirtualLoop) -> None:
    """The third ed2k keyword waits for the first two, then still polls to its end."""
    api = _hour_of_three_keywords(virtual_loop)

    for search_id, (_, query) in api.searches.items():
        assert _polled_until(api, search_id) >= _DURATIONS[query], (search_id, query)


def test_an_hour_of_searches_never_stops_nor_frees_one(virtual_loop: VirtualLoop) -> None:
    api = _hour_of_three_keywords(virtual_loop)

    assert [r for r in api.requests if r.url.path.endswith("/stop")] == []
    assert [r for r in api.requests if r.method == "DELETE"] == []


def test_an_ed2k_search_that_never_finishes_holds_the_next_start_one_budget(
    virtual_loop: VirtualLoop,
) -> None:
    api = _api(virtual_loop, progress={"state": "running"})

    async def main() -> None:
        client = await _connected(api)
        await asyncio.gather(
            client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=_BUDGET),
            client.search(Keyword("titar"), channel=Channel("ed2k"), budget_seconds=_BUDGET),
        )

    virtual_loop.run_until_complete(main())

    assert [moment for moment, _ in _starts(api, "global")] == [0, _BUDGET]


def test_concurrent_callers_of_one_kad_target_each_get_their_own_slot(
    virtual_loop: VirtualLoop,
) -> None:
    api = _api(virtual_loop)

    async def main() -> None:
        client = await _connected(api)
        await client.search(Keyword("keroro"), channel=Channel("kad"), budget_seconds=_BUDGET)
        # Both wait for the target's next slot: whoever wakes first must not leave it free.
        await asyncio.gather(
            client.search(Keyword("keroro 1"), channel=Channel("kad"), budget_seconds=_BUDGET),
            client.search(Keyword("keroro 2"), channel=Channel("kad"), budget_seconds=_BUDGET),
        )

    virtual_loop.run_until_complete(main())

    assert [moment for moment, _ in _starts(api, "kad")] == [0, 60, 120]


@pytest.mark.parametrize(
    ("first", "second", "shared"),
    [
        (Keyword("keroro 62"), Keyword("keroro mission"), True),
        (Keyword("Keroro.062"), Keyword("[VF] KERORO"), True),
        (Keyword("62 keroro"), Keyword("keroro"), True),
        (Keyword("ok/titar"), Keyword("titar"), True),
        (Keyword("été"), Keyword("ÉTÉ"), True),
        (Keyword("éa"), Keyword("éa titar"), True),  # 3 UTF-8 bytes in 2 characters: a word for Kad
        (Keyword("keroro"), Keyword("titar"), False),
        (Keyword("keroros"), Keyword("keroro"), False),
    ],
)
def test_kad_keys_a_keyword_on_its_first_word_of_three_bytes(
    first: Keyword, second: Keyword, shared: bool, virtual_loop: VirtualLoop
) -> None:
    api = _api(virtual_loop)

    async def main() -> None:
        client = await _connected(api)
        await client.search(first, channel=Channel("kad"), budget_seconds=_BUDGET)
        await client.search(second, channel=Channel("kad"), budget_seconds=_BUDGET)

    virtual_loop.run_until_complete(main())

    assert [moment for moment, _ in _starts(api, "kad")] == [0, 60 if shared else 0]


@pytest.mark.parametrize(
    "keyword", [Keyword("62"), Keyword("ok"), Keyword("é"), Keyword("62 ok"), Keyword("VF-62")]
)
def test_a_keyword_without_a_kad_target_neither_spins_nor_searches(
    keyword: Keyword, virtual_loop: VirtualLoop
) -> None:
    api = _api(virtual_loop)
    returned_at: list[float] = []

    async def main() -> None:
        client = await _connected(api)
        loop = asyncio.get_running_loop()
        while loop.time() < _HOUR and len(returned_at) <= 60:  # bounded, should it spin
            assert await client.search(
                keyword, channel=Channel("kad"), budget_seconds=_BUDGET
            ) == SearchAnswer(reported_files=(), skipped_result_count=0)
            returned_at.append(loop.time())
            await asyncio.sleep(0)  # noqa: TID251

    virtual_loop.run_until_complete(main())

    assert len([moment for moment in returned_at if moment < _HOUR]) == 60
    assert _starts(api, "kad") == []


def test_a_keyword_without_a_kad_target_is_logged_once(
    caplog: pytest.LogCaptureFixture, virtual_loop: VirtualLoop
) -> None:
    caplog.set_level(logging.INFO, logger="p2pwatch.adapters.driven.amule_api.amule_api_client")

    async def main() -> None:
        client = await _connected(_api(virtual_loop))
        for keyword in (Keyword("62"), Keyword("62"), Keyword("ok"), Keyword("62")):
            await client.search(keyword, channel=Channel("kad"), budget_seconds=_BUDGET)

    virtual_loop.run_until_complete(main())

    assert [record.getMessage().count("no Kad word") for record in caplog.records] == [1, 1]
    assert ["'62'" in record.getMessage() for record in caplog.records] == [True, False]


def test_a_kad_target_held_elsewhere_is_retried_each_poll_until_it_frees(
    virtual_loop: VirtualLoop,
) -> None:
    api = _api(virtual_loop, search_seconds={"keroro": 30})
    refusals = [error(400, code="amuled_rejected", message=_ALREADY_SEARCHING)] * 2
    api.overrides[("POST", "/api/v1/search")] = lambda request: (
        refusals.pop(0) if refusals else api._start_search(request)
    )

    async def main() -> None:
        client = await _connected(api)
        await client.search(Keyword("keroro"), channel=Channel("kad"), budget_seconds=_BUDGET)

    virtual_loop.run_until_complete(main())

    assert [moment for moment, _ in _starts(api, "kad")] == [0, 5, 10]
    assert _polled_until(api, 42) >= 30  # its budget runs from the start at 10 s


def test_a_kad_target_held_past_one_budget_fails_the_channel_at_that_budget(
    virtual_loop: VirtualLoop,
) -> None:
    api = _api(virtual_loop)
    api.overrides[("POST", "/api/v1/search")] = lambda _: error(
        400, code="amuled_rejected", message=_ALREADY_SEARCHING
    )
    failed_at: list[float] = []

    async def main() -> None:
        client = await _connected(api)
        with pytest.raises(SearchFailedError):
            await client.search(Keyword("keroro"), channel=Channel("kad"), budget_seconds=_BUDGET)
        failed_at.append(asyncio.get_running_loop().time())

    virtual_loop.run_until_complete(main())

    assert failed_at == [_BUDGET]
    assert [moment for moment, _ in _starts(api, "kad")][-2:] == [_BUDGET - 5, _BUDGET]


def test_any_other_kad_refusal_fails_the_channel_at_once(virtual_loop: VirtualLoop) -> None:
    api = _api(virtual_loop)
    api.overrides[("POST", "/api/v1/search")] = lambda _: error(
        400, code="amuled_rejected", message="Kad is not running"
    )

    async def main() -> None:
        client = await _connected(api)
        with pytest.raises(SearchFailedError):
            await client.search(Keyword("keroro"), channel=Channel("kad"), budget_seconds=_BUDGET)

    virtual_loop.run_until_complete(main())

    assert len(_starts(api, "kad")) == 1
