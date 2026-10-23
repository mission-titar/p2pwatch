"""The status loop: a reading every minute feeds the channel gauges, and a degraded state alerts
once it has lasted, whatever came before it, boot included (spec stage 2, D15)."""

import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.status_loop import StatusLoopDeps, status_loop
from p2pwatch.domain.client_errors import ClientAuthError, ClientError, ReadRejectedError
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.policy import Severity
from p2pwatch.domain.status_reading import (
    ChannelStatus,
    ClientStatus,
    PublishedReading,
    StatusReading,
)
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_metrics_recorder import FakeMetricsRecorder
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_status_client import FakeStatusClient
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore
from tests.fakes.adapters.driven.fake_stepped_status_client import FakeSteppedStatusClient
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_timed_notifier import FakeTimedNotifier

type _Reading = ClientStatus | ClientError

_UP = (True, True)
_LOW_ID = (True, False)  # on the network, not connectable
_DOWN = make_unreachable()
_NODE = "titar-node-1"
_NOTIFICATION_TIMEOUT_SECONDS = 5.0


class _Observability:
    """The dispatch step over fakes, each notification timed: an alert is one."""

    def __init__(self, fake_time: FakeTime) -> None:
        self.logger = FakeLogger()
        self.notifier = FakeTimedNotifier(fake_time)
        self.dispatcher = ObservabilityDispatcher(
            logger=self.logger,
            metrics_recorder=FakeMetricsRecorder(),
            notifier=self.notifier,
            notification_timeout_seconds=_NOTIFICATION_TIMEOUT_SECONDS,
        )


def _status(**channels: tuple[bool, bool | None]) -> ClientStatus:
    return ClientStatus(
        "3.0.1",
        tuple(ChannelStatus(name, on, connectable) for name, (on, connectable) in channels.items()),
    )


def _deps(
    client_name: str,
    client: StatusClient,
    fake_time: FakeTime,
    observability: _Observability,
    run_state: FakeRunStateStore,
) -> StatusLoopDeps:
    return StatusLoopDeps(
        client_name,
        client,
        fake_time.wall,
        fake_time.monotonic,
        observability.dispatcher,
        run_state,
        FakeStatusReadingStore(),
    )


async def _run(*readings: _Reading, client: str = "amuled") -> _Observability:
    fake_time, run_state = FakeTime(), FakeRunStateStore()
    observability = _Observability(fake_time)
    scripted = FakeStatusClient(list(readings), run_state)
    await asyncio.wait_for(
        status_loop(_deps(client, scripted, fake_time, observability, run_state), _NODE),
        timeout=1.0,
    )
    return observability


@pytest.mark.asyncio
async def test_every_alert_is_notified_under_the_node_id_the_loop_runs_with() -> None:
    observability = await _run(_DOWN, _DOWN, _DOWN, _status(ed2k=_UP))
    notifications = observability.notifier.notifications
    assert notifications
    assert {notification.node_id for _, notification in notifications} == {_NODE}


async def _alerts(*readings: _Reading) -> list[tuple[float, Notification]]:
    return (await _run(*readings)).notifier.notifications


def _warning(message: str) -> RelayedLogLine:
    return RelayedLogLine(message, Severity.WARNING, _NODE)


def _info(message: str) -> RelayedLogLine:
    return RelayedLogLine(message, Severity.INFO, _NODE)


_NOT_CONNECTABLE = "not connectable for 5 min"


@pytest.mark.asyncio
async def test_not_connectable_from_the_first_reading_alerts_at_five_minutes_once() -> None:
    alerts = await _alerts(*[_status(ed2k=_LOW_ID)] * 10)
    assert alerts == [(300.0, _warning(f"amuled ed2k: {_NOT_CONNECTABLE}"))]


@pytest.mark.asyncio
async def test_a_degraded_state_lasting_four_minutes_never_alerts_nor_recovers() -> None:
    alerts = await _alerts(*[_status(ed2k=_LOW_ID)] * 5, _status(ed2k=_UP))
    assert alerts == []


@pytest.mark.asyncio
async def test_off_the_network_alerts_whatever_the_client_and_channel() -> None:
    observability = await _run(*[_status(x=(False, None))] * 6, client="fake")
    assert observability.notifier.notifications == [
        (300.0, _warning("fake x: off its network for 5 min"))
    ]


@pytest.mark.asyncio
async def test_a_good_reading_after_an_alert_recovers() -> None:
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, _status(kad=_UP))
    assert alerts == [
        (300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}")),
        (360.0, _info("amuled kad: connectable again")),
    ]


@pytest.mark.asyncio
async def test_unknown_between_two_degraded_readings_restarts_the_clock() -> None:
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 3, unknown, *[_status(kad=_LOW_ID)] * 6)
    assert alerts == [(540.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}"))]


@pytest.mark.asyncio
async def test_unknown_after_an_alert_is_no_recovery() -> None:
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, unknown, _status(kad=_UP))
    assert alerts == [
        (300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}")),
        (420.0, _info("amuled kad: connectable again")),
    ]


@pytest.mark.asyncio
async def test_unreachable_alerts_at_two_minutes_and_recovers_when_it_answers() -> None:
    observability = await _run(_DOWN, _DOWN, _DOWN, _status(ed2k=_UP))
    assert observability.notifier.notifications == [
        (120.0, _warning("amuled unreachable for 2 min")),
        (180.0, _info("amuled reachable again")),
    ]
    assert observability.logger.lines.count(LoggedLine("warning", "amuled unreachable")) == 3


@pytest.mark.asyncio
async def test_an_operation_the_api_refuses_reads_as_unreachable() -> None:
    # A route a weekly aMule bump renamed: /version answers 404 not_found.
    refused = ReadRejectedError("GET /api/v1/version: 404 not_found: no route")
    alerts = await _alerts(refused, refused, refused)
    assert alerts == [(120.0, _warning("amuled unreachable for 2 min"))]


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
        (360.0, _warning("amuled unreachable for 2 min")),
        (540.0, _info("amuled reachable again")),
        (840.0, _warning(f"amuled ed2k: {_NOT_CONNECTABLE}")),
    ]


@pytest.mark.asyncio
async def test_each_reading_samples_every_channel_and_unreachable_makes_them_unknown() -> None:
    observability = await _run(_DOWN, _status(ed2k=_UP, kad=(False, None)), _DOWN)
    assert observability.logger.lines == [
        LoggedLine("warning", "amuled unreachable"),
        LoggedLine("debug", "status amuled ed2k: connected yes, connectable yes"),
        LoggedLine("debug", "status amuled kad: connected no, connectable unknown"),
        LoggedLine("warning", "amuled unreachable"),
        LoggedLine("debug", "status amuled ed2k: connected unknown, connectable unknown"),
        LoggedLine("debug", "status amuled kad: connected unknown, connectable unknown"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reading", "published"), [(_status(ed2k=_UP), _status(ed2k=_UP)), (_DOWN, None)]
)
async def test_each_reading_is_published_with_its_wall_and_monotonic_instants(
    reading: _Reading, published: ClientStatus | None
) -> None:
    fake_time, run_state = FakeTime(), FakeRunStateStore()
    fake_time.step_wall(timedelta(hours=1))  # the two clocks part: each instant shows its clock
    status_reading_store = FakeStatusReadingStore()
    client = FakeStatusClient([_status(kad=_UP), reading], run_state)
    deps = _deps("amuled", client, fake_time, _Observability(fake_time), run_state)
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
    fake_time, run_state = FakeTime(), FakeRunStateStore()
    observability = _Observability(fake_time)
    client = FakeSteppedStatusClient([_status(ed2k=_LOW_ID)] * 5, run_state, fake_time)
    await asyncio.wait_for(
        status_loop(_deps("amuled", client, fake_time, observability, run_state), _NODE),
        timeout=1.0,
    )
    assert observability.notifier.notifications == []
