"""The status loop: a reading every minute feeds the channel gauges, and a degraded state alerts
once it has lasted, whatever came before it, boot included (spec stage 2, D15)."""

import asyncio
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.mule_api.errors import ApiAuthError, ApiRejectedError
from p2pwatch.application.status_loop import (
    StatusBoard,
    StatusLoopDeps,
    status_loop,
)
from p2pwatch.domain.observability import events as ev
from p2pwatch.ports.driven.client_errors import ClientError
from p2pwatch.ports.driven.client_status import (
    ChannelStatus,
    ClientStatus,
    StatusClient,
    StatusReading,
)
from p2pwatch_testing.application.fakes import FakeTime, make_unreachable

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


def _status(**channels: tuple[bool, bool | None]) -> ClientStatus:
    return ClientStatus(
        "3.0.1",
        tuple(ChannelStatus(name, on, connectable) for name, (on, connectable) in channels.items()),
    )


class _ScriptedClient:
    """One scripted reading per call; the last one asks for shutdown."""

    def __init__(self, readings: list[_Reading], shutdown: asyncio.Event) -> None:
        self._readings = readings
        self._shutdown = shutdown

    async def status(self) -> ClientStatus:
        reading = self._readings.pop(0)
        if not self._readings:
            self._shutdown.set()
        if isinstance(reading, ClientError):
            raise reading
        return reading


class _SteppedClient(_ScriptedClient):
    """Steps the wall clock forward an hour between its first reading and its second."""

    def __init__(
        self, readings: list[_Reading], shutdown: asyncio.Event, fake_time: FakeTime
    ) -> None:
        super().__init__(readings, shutdown)
        self._fake_time = fake_time
        self._calls = 0

    async def status(self) -> ClientStatus:
        self._calls += 1
        if self._calls == 2:
            self._fake_time.step_wall(timedelta(hours=1))
        return await super().status()


class _TimedTelemetry:
    """Each event with the seconds elapsed on the monotonic clock when it was emitted."""

    def __init__(self, fake_time: FakeTime) -> None:
        self._fake_time = fake_time
        self._start = fake_time.monotonic.now()
        self.events: list[tuple[float, ev.Event]] = []

    async def emit(self, event: ev.Event) -> None:
        elapsed = self._fake_time.monotonic.now() - self._start
        self.events.append((elapsed.total_seconds(), event))


def _deps(
    client_name: str,
    client: StatusClient,
    fake_time: FakeTime,
    telemetry: _TimedTelemetry,
    shutdown: asyncio.Event,
) -> StatusLoopDeps:
    board = StatusBoard((client_name,), fake_time.monotonic)
    return StatusLoopDeps(
        client_name, client, fake_time.wall, fake_time.monotonic, telemetry, shutdown, board
    )


async def _run(*readings: _Reading, client: str = "amuled") -> list[tuple[float, ev.Event]]:
    fake_time, shutdown = FakeTime(), asyncio.Event()
    telemetry = _TimedTelemetry(fake_time)
    scripted = _ScriptedClient(list(readings), shutdown)
    await asyncio.wait_for(
        status_loop(_deps(client, scripted, fake_time, telemetry, shutdown)), timeout=1.0
    )
    return telemetry.events


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
    refused = ApiRejectedError("GET /api/v1/version: 404 not_found: no route")
    events = await _run(refused, refused, refused)
    assert (120.0, ev.ClientUnreachableLasting("amuled", 120.0)) in events


@pytest.mark.asyncio
async def test_a_refused_password_ends_the_loop() -> None:
    with pytest.raises(ApiAuthError):
        await _run(ApiAuthError("amuleapi refused the admin password"), _status(ed2k=_UP))


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
async def test_each_reading_is_published_with_its_time(
    reading: _Reading, published: ClientStatus | None
) -> None:
    fake_time, shutdown = FakeTime(), asyncio.Event()
    client = _ScriptedClient([_status(kad=_UP), reading], shutdown)
    deps = _deps("amuled", client, fake_time, _TimedTelemetry(fake_time), shutdown)
    assert deps.board.readings() == {"amuled": None}
    await asyncio.wait_for(status_loop(deps), timeout=1.0)
    read_at = fake_time.wall.now() - timedelta(seconds=60)  # the loop slept one period after it
    assert deps.board.readings() == {"amuled": StatusReading(read_at, published)}


@pytest.mark.asyncio
async def test_a_wall_clock_step_forward_raises_no_alert_before_its_delay() -> None:
    # Degraded for four minutes of monotonic time, an hour and four minutes of wall clock.
    fake_time, shutdown = FakeTime(), asyncio.Event()
    telemetry = _TimedTelemetry(fake_time)
    client = _SteppedClient([_status(ed2k=_LOW_ID)] * 5, shutdown, fake_time)
    await asyncio.wait_for(
        status_loop(_deps("amuled", client, fake_time, telemetry, shutdown)), timeout=1.0
    )
    assert [e for _, e in telemetry.events if isinstance(e, _ALERTS)] == []


def test_a_reading_older_than_two_status_periods_is_not_current() -> None:
    fake_time = FakeTime()
    board = StatusBoard(("amuled",), fake_time.monotonic)
    board.publish("amuled", StatusReading(fake_time.wall.now(), None))
    fake_time.advance(timedelta(seconds=120))
    assert board.is_current("amuled")
    fake_time.advance(timedelta(seconds=1))
    assert not board.is_current("amuled")


def test_a_wall_clock_step_forward_leaves_a_reading_a_second_old_current() -> None:
    fake_time = FakeTime()
    board = StatusBoard(("amuled",), fake_time.monotonic)
    board.publish("amuled", StatusReading(fake_time.wall.now(), None))
    fake_time.advance(timedelta(seconds=1))
    fake_time.step_wall(timedelta(hours=1))
    assert board.is_current("amuled")


def test_a_client_not_read_yet_is_not_current() -> None:
    assert not StatusBoard(("amuled",), FakeTime().monotonic).is_current("amuled")


def test_publishing_replaces_the_snapshot_and_never_changes_one_already_read() -> None:
    fake_time = FakeTime()
    board = StatusBoard(("amuled",), fake_time.monotonic)
    before = board.readings()
    board.publish("amuled", StatusReading(fake_time.wall.now(), None))
    assert before == {"amuled": None}
