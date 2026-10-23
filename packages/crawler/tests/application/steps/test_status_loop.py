"""The status loop: a reading every minute feeds the channel gauges, and a degraded state alerts
once it has lasted, whatever came before it, boot included (spec stage 2, D15)."""

import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.steps.status_loop import StatusLoopDeps, status_loop
from p2pwatch.domain.client_errors import ClientAuthError, ClientError, ReadRejectedError
from p2pwatch.domain.observability import events as ev
from p2pwatch.domain.status_reading import (
    ChannelStatus,
    ClientStatus,
    PublishedReading,
    StatusReading,
)
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_status_client import FakeStatusClient
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore
from tests.fakes.adapters.driven.fake_stepped_status_client import FakeSteppedStatusClient
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_timed_event_emitter import FakeTimedEventEmitter

type _Reading = ClientStatus | ClientError

_ALERTS = (
    ev.ChannelDegraded,
    ev.ChannelRecovered,
    ev.ClientUnreachableLasting,
    ev.ClientReachableAgain,
)
_UP = (True, True)
_LOW_ID = (True, False)  # on the network, not connectable
_DOWN = make_unreachable()
_NODE = "titar-node-1"


def _status(**channels: tuple[bool, bool | None]) -> ClientStatus:
    return ClientStatus(
        "3.0.1",
        tuple(ChannelStatus(name, on, connectable) for name, (on, connectable) in channels.items()),
    )


def _deps(
    client_name: str,
    client: StatusClient,
    fake_time: FakeTime,
    event_emitter: FakeTimedEventEmitter,
    shutdown: asyncio.Event,
) -> StatusLoopDeps:
    return StatusLoopDeps(
        client_name,
        client,
        fake_time.wall,
        fake_time.monotonic,
        event_emitter,
        shutdown,
        FakeStatusReadingStore(),
    )


async def _run(*readings: _Reading, client: str = "amuled") -> list[tuple[float, ev.Event]]:
    fake_time, shutdown = FakeTime(), asyncio.Event()
    event_emitter = FakeTimedEventEmitter(fake_time)
    scripted = FakeStatusClient(list(readings), shutdown)
    await asyncio.wait_for(
        status_loop(_deps(client, scripted, fake_time, event_emitter, shutdown), _NODE), timeout=1.0
    )
    return event_emitter.events


@pytest.mark.asyncio
async def test_every_event_is_emitted_under_the_node_id_the_loop_runs_with() -> None:
    fake_time, shutdown = FakeTime(), asyncio.Event()
    event_emitter = FakeTimedEventEmitter(fake_time)
    readings: list[_Reading] = [_DOWN, _DOWN, _DOWN, _status(ed2k=_UP)]
    client = FakeStatusClient(readings, shutdown)
    await asyncio.wait_for(
        status_loop(_deps("amuled", client, fake_time, event_emitter, shutdown), _NODE), timeout=1.0
    )
    assert any(isinstance(event, _ALERTS) for _, event in event_emitter.events)
    assert event_emitter.node_ids == {_NODE}


async def _alerts(*readings: _Reading) -> list[tuple[float, ev.Event]]:
    return [(at, event) for at, event in await _run(*readings) if isinstance(event, _ALERTS)]


def _degraded(channel: str, field: ev.ChannelField) -> ev.ChannelDegraded:
    return ev.ChannelDegraded("amuled", channel, field, 300.0)


@pytest.mark.asyncio
async def test_not_connectable_from_the_first_reading_alerts_at_five_minutes_once() -> None:
    alerts = await _alerts(*[_status(ed2k=_LOW_ID)] * 10)
    assert alerts == [(300.0, _degraded("ed2k", "connectable"))]


@pytest.mark.asyncio
async def test_a_degraded_state_lasting_four_minutes_never_alerts_nor_recovers() -> None:
    alerts = await _alerts(*[_status(ed2k=_LOW_ID)] * 5, _status(ed2k=_UP))
    assert alerts == []


@pytest.mark.asyncio
async def test_off_the_network_alerts_whatever_the_client_and_channel() -> None:
    events = await _run(*[_status(x=(False, None))] * 6, client="fake")
    assert [e for _, e in events if isinstance(e, _ALERTS)] == [
        ev.ChannelDegraded("fake", "x", "connected", 300.0)
    ]


@pytest.mark.asyncio
async def test_a_good_reading_after_an_alert_recovers() -> None:
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, _status(kad=_UP))
    assert alerts == [
        (300.0, _degraded("kad", "connectable")),
        (360.0, ev.ChannelRecovered("amuled", "kad", "connectable")),
    ]


@pytest.mark.asyncio
async def test_unknown_between_two_degraded_readings_restarts_the_clock() -> None:
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 3, unknown, *[_status(kad=_LOW_ID)] * 6)
    assert alerts == [(540.0, _degraded("kad", "connectable"))]


@pytest.mark.asyncio
async def test_unknown_after_an_alert_is_no_recovery() -> None:
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, unknown, _status(kad=_UP))
    assert alerts == [
        (300.0, _degraded("kad", "connectable")),
        (420.0, ev.ChannelRecovered("amuled", "kad", "connectable")),
    ]


@pytest.mark.asyncio
async def test_unreachable_alerts_at_two_minutes_and_recovers_when_it_answers() -> None:
    events = await _run(_DOWN, _DOWN, _DOWN, _status(ed2k=_UP))
    assert [(at, e) for at, e in events if isinstance(e, _ALERTS)] == [
        (120.0, ev.ClientUnreachableLasting("amuled", 120.0)),
        (180.0, ev.ClientReachableAgain("amuled")),
    ]
    assert [e for _, e in events].count(ev.ClientUnreachable("amuled")) == 3


@pytest.mark.asyncio
async def test_an_operation_the_api_refuses_reads_as_unreachable() -> None:
    # A route a weekly aMule bump renamed: /version answers 404 not_found.
    refused = ReadRejectedError("GET /api/v1/version: 404 not_found: no route")
    events = await _run(refused, refused, refused)
    assert (120.0, ev.ClientUnreachableLasting("amuled", 120.0)) in events


@pytest.mark.asyncio
async def test_a_refused_password_ends_the_loop() -> None:
    with pytest.raises(ClientAuthError):
        await _run(ClientAuthError("amuleapi refused the admin password"), _status(ed2k=_UP))


@pytest.mark.asyncio
async def test_unreachable_for_one_minute_never_alerts() -> None:
    assert await _alerts(_DOWN, _DOWN, _status(ed2k=_UP)) == []


@pytest.mark.asyncio
async def test_while_unreachable_only_the_api_alerts_and_channel_clocks_restart() -> None:
    low = _status(ed2k=_LOW_ID)
    alerts = await _alerts(*[low] * 4, *[_DOWN] * 5, *[low] * 6)
    assert alerts == [
        (360.0, ev.ClientUnreachableLasting("amuled", 120.0)),
        (540.0, ev.ClientReachableAgain("amuled")),
        (840.0, _degraded("ed2k", "connectable")),
    ]


@pytest.mark.asyncio
async def test_each_reading_samples_every_channel_and_unreachable_makes_them_unknown() -> None:
    events = await _run(_DOWN, _status(ed2k=_UP, kad=(False, None)), _DOWN)
    assert [(at, e) for at, e in events if isinstance(e, ev.ChannelStatusSampled)] == [
        (60.0, ev.ChannelStatusSampled("amuled", "ed2k", True, True)),
        (60.0, ev.ChannelStatusSampled("amuled", "kad", False, None)),
        (120.0, ev.ChannelStatusSampled("amuled", "ed2k", None, None)),
        (120.0, ev.ChannelStatusSampled("amuled", "kad", None, None)),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reading", "published"), [(_status(ed2k=_UP), _status(ed2k=_UP)), (_DOWN, None)]
)
async def test_each_reading_is_published_with_its_wall_and_monotonic_instants(
    reading: _Reading, published: ClientStatus | None
) -> None:
    fake_time, shutdown = FakeTime(), asyncio.Event()
    fake_time.step_wall(timedelta(hours=1))  # the two clocks part: each instant shows its clock
    status_reading_store = FakeStatusReadingStore()
    client = FakeStatusClient([_status(kad=_UP), reading], shutdown)
    deps = _deps("amuled", client, fake_time, FakeTimedEventEmitter(fake_time), shutdown)
    deps.status_reading_writer = status_reading_store
    await asyncio.wait_for(status_loop(deps, _NODE), timeout=1.0)
    read_at = fake_time.wall.now() - timedelta(seconds=60)  # the loop slept one period after it
    published_at = fake_time.monotonic.now() - timedelta(seconds=60)
    assert status_reading_store.read_readings() == {
        "amuled": PublishedReading(StatusReading(read_at, published), published_at)
    }


@pytest.mark.asyncio
async def test_a_wall_clock_step_forward_raises_no_alert_before_its_delay() -> None:
    # Degraded for four minutes of monotonic time, an hour and four minutes of wall clock.
    fake_time, shutdown = FakeTime(), asyncio.Event()
    event_emitter = FakeTimedEventEmitter(fake_time)
    client = FakeSteppedStatusClient([_status(ed2k=_LOW_ID)] * 5, shutdown, fake_time)
    await asyncio.wait_for(
        status_loop(_deps("amuled", client, fake_time, event_emitter, shutdown), _NODE),
        timeout=1.0,
    )
    assert [e for _, e in event_emitter.events if isinstance(e, _ALERTS)] == []
