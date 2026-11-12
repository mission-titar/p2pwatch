"""The status sensor, a work: a reading every minute feeds the channel gauges and the conditions of
the client and of each channel, whose transitions send today's alerts (spec stage 2, D15; v5 lot 4,
D21)."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.application.steps.health_event_translator import HealthEventTranslator
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.status_sensor import StatusSensor
from p2pwatch.application.steps.supervisor import SupervisedWork, Supervisor
from p2pwatch.domain.client_errors import ClientAuthError, ClientError, ReadRejectedError
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import (
    ChannelStatus,
    ClientStatus,
    PublishedReading,
    StatusReading,
    channel_component,
    client_component,
)
from p2pwatch.domain.work_components import download_tracking_component, status_sensor_component
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_loop_wall_clock import FakeLoopWallClock
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_status_client import FakeStatusClient
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore
from tests.fakes.adapters.driven.fake_stepped_status_client import FakeSteppedStatusClient
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_timed_notifier import FakeTimedNotifier
from tests.support.virtual_time import VirtualLoop

type _Reading = ClientStatus | ClientError

_UP = (True, True)
_LOW_ID = (True, False)  # on the network, not connectable
_DOWN = make_unreachable()
_NODE_ID = NodeId("titar-node-1")
_AMULED = ClientName("amuled")
_CHANNELS = (Channel("ed2k"), Channel("kad"))
_NOTIFICATION_TIMEOUT_SECONDS = 5.0


class _Observability:
    """The dispatch step over fakes, each notification timed: an alert is one; the health recorder
    logs apart, as its own module's logger does."""

    def __init__(self, fake_time: FakeTime) -> None:
        self.logger = FakeLogger()
        self.notifier = FakeTimedNotifier(fake_time)
        self.dispatcher = ObservabilityDispatcher(
            logger=self.logger,
            node_metric_writer=FakeNodeMetricStore(),
            notifier=self.notifier,
            notification_timeout_seconds=_NOTIFICATION_TIMEOUT_SECONDS,
        )
        self.health_logger = FakeLogger()
        translator = HealthEventTranslator(
            observability_dispatcher=self.dispatcher, node_id=_NODE_ID
        )
        self.health_recorder = HealthRecorder(
            logger=self.health_logger, subscribers=(translator.translate,)
        )


def _status(**channels: tuple[bool, bool | None]) -> ClientStatus:
    return ClientStatus(
        version="3.0.1",
        channels=tuple(
            ChannelStatus(channel=Channel(name), connected=on, connectable=connectable)
            for name, (on, connectable) in channels.items()
        ),
    )


def _status_sensor(
    client_name: ClientName,
    *,
    client: StatusClient,
    fake_time: FakeTime,
    observability: _Observability,
    status_reading_writer: StatusReadingWriter | None = None,
    channels: Sequence[Channel] = _CHANNELS,
    download: bool = False,
) -> StatusSensor:
    return StatusSensor(
        client_name=client_name,
        client=client,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        observability_dispatcher=observability.dispatcher,
        status_reading_writer=status_reading_writer or FakeStatusReadingStore((client_name,)),
        health_recorder=observability.health_recorder,
        client_component=client_component(client_name),
        channel_components={
            channel: channel_component(client_name=client_name, channel=channel)
            for channel in channels
        },
        download_tracking_component=download_tracking_component(client_name) if download else None,
    )


async def _take_turns(sensor: StatusSensor, *, turns: int) -> None:
    for _ in range(turns):
        await sensor.wait_for_next_turn()
        await sensor.run_once()


async def _run(
    *readings: _Reading,
    client: ClientName = _AMULED,
    channels: Sequence[Channel] = _CHANNELS,
    download: bool = False,
) -> _Observability:
    fake_time = FakeTime()
    observability = _Observability(fake_time)
    sensor = _status_sensor(
        client,
        client=FakeStatusClient(list(readings)),
        fake_time=fake_time,
        observability=observability,
        channels=channels,
        download=download,
    )
    await _take_turns(sensor, turns=len(readings))
    return observability


@pytest.mark.asyncio
async def test_every_alert_is_notified_under_the_node_id_the_loop_is_built_with() -> None:
    observability = await _run(_DOWN, _DOWN, _DOWN, _status(ed2k=_UP))
    notifications = observability.notifier.notifications
    assert notifications
    assert {notification.node_id for _, notification in notifications} == {_NODE_ID}


async def _alerts(*readings: _Reading) -> list[tuple[float, Notification]]:
    return (await _run(*readings)).notifier.notifications


def _warning(message: str) -> RelayedLogLine:
    return RelayedLogLine(message=message, severity=Severity.WARNING, node_id=_NODE_ID)


def _info(message: str) -> RelayedLogLine:
    return RelayedLogLine(message=message, severity=Severity.INFO, node_id=_NODE_ID)


_NOT_CONNECTABLE = "not connectable for 5 min"


@pytest.mark.asyncio
async def test_a_connected_channel_not_connectable_alerts_on_that_field_alone_at_six_readings() -> (
    None
):
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 10)
    assert alerts == [(300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}"))]


@pytest.mark.asyncio
async def test_a_degraded_state_lasting_four_minutes_never_alerts_nor_recovers() -> None:
    alerts = await _alerts(*[_status(ed2k=_LOW_ID)] * 5, _status(ed2k=_UP))
    assert alerts == []


@pytest.mark.asyncio
async def test_off_the_network_alerts_whatever_the_client_and_channel() -> None:
    observability = await _run(
        *[_status(x=(False, None))] * 6, client=ClientName("fake"), channels=(Channel("x"),)
    )
    assert observability.notifier.notifications == [
        (300.0, _warning("fake x: off its network for 5 min"))
    ]


@pytest.mark.asyncio
async def test_off_the_network_ends_at_the_ninth_reading_back_on_it() -> None:
    # Ends under 2 failures among the last 10 readings: the eighth still sees two.
    alerts = await _alerts(*[_status(kad=(False, None))] * 6, *[_status(kad=_UP)] * 9)
    assert alerts == [
        (300.0, _warning("amuled kad: off its network for 5 min")),
        (840.0, _info("amuled kad: back on its network")),
    ]


@pytest.mark.asyncio
async def test_not_connectable_ends_at_the_twentieth_connectable_reading() -> None:
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, *[_status(kad=_UP)] * 20)
    assert alerts == [
        (300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}")),
        (1500.0, _info("amuled kad: connectable again")),
    ]


@pytest.mark.asyncio
async def test_an_unknown_field_between_two_degraded_runs_records_nothing() -> None:
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 3, unknown, *[_status(kad=_LOW_ID)] * 3)
    assert alerts == [(360.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}"))]


@pytest.mark.asyncio
async def test_an_unknown_field_after_an_alert_is_no_recovery() -> None:
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, unknown, *[_status(kad=_UP)] * 20)
    assert alerts == [
        (300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}")),
        (1560.0, _info("amuled kad: connectable again")),
    ]


@pytest.mark.asyncio
async def test_an_unreachable_reading_between_two_failed_runs_sends_no_end_nor_second_alert() -> (
    None
):
    off = _status(kad=(False, None))
    alerts = await _alerts(*[off] * 6, _DOWN, *[off] * 6)
    assert alerts == [(300.0, _warning("amuled kad: off its network for 5 min"))]


@pytest.mark.asyncio
async def test_unreachable_alerts_at_two_minutes_and_ends_at_the_ninth_answer() -> None:
    # Ends under 2 unanswered among the last 10 readings: the eighth answer still sees two.
    observability = await _run(_DOWN, _DOWN, _DOWN, *[_status(ed2k=_UP)] * 9)
    assert observability.notifier.notifications == [
        (120.0, _warning("amuled unreachable for 2 min")),
        (660.0, _info("amuled reachable again")),
    ]
    assert (
        observability.logger.lines.count(LoggedLine(level="warning", message="amuled unreachable"))
        == 3
    )


@pytest.mark.asyncio
async def test_eight_answers_after_an_unreachable_alert_end_nothing() -> None:
    alerts = await _alerts(_DOWN, _DOWN, _DOWN, *[_status(ed2k=_UP)] * 8)
    assert alerts == [(120.0, _warning("amuled unreachable for 2 min"))]


@pytest.mark.asyncio
async def test_unreachable_fails_the_client_s_unreachable_condition_at_its_third_reading() -> None:
    observability = await _run(_DOWN, _DOWN, _DOWN)
    assert observability.health_logger.lines == [
        LoggedLine(level="warning", message="client amuled, unreachable: unknown to failing")
    ]


def _download_tracking_lines(observability: _Observability) -> list[LoggedLine]:
    return [
        line
        for line in observability.health_logger.lines
        if line.message.startswith("download tracking")
    ]


@pytest.mark.asyncio
async def test_a_client_connected_to_no_network_fails_download_tracking_at_its_third_reading() -> (
    None
):
    off = _status(ed2k=(False, None), kad=(False, None))
    observability = await _run(off, off, off, download=True)
    assert _download_tracking_lines(observability) == [
        LoggedLine(
            level="warning",
            message="download tracking amuled, connected to no network: unknown to failing",
        )
    ]
    assert observability.notifier.notifications == []  # its first reader is the log line


@pytest.mark.asyncio
async def test_one_channel_connected_keeps_download_tracking_connected() -> None:
    half = _status(ed2k=_UP, kad=(False, None))
    observability = await _run(half, half, half, download=True)
    assert _download_tracking_lines(observability) == [
        LoggedLine(
            level="info",
            message="download tracking amuled, connected to no network: unknown to healthy",
        )
    ]


@pytest.mark.asyncio
async def test_an_unanswered_reading_records_nothing_on_download_tracking() -> None:
    off = _status(ed2k=(False, None), kad=(False, None))
    observability = await _run(off, off, _DOWN, _DOWN, _DOWN, off, download=True)
    assert _download_tracking_lines(observability) == [
        LoggedLine(
            level="warning",
            message="download tracking amuled, connected to no network: unknown to failing",
        )
    ]


@pytest.mark.asyncio
async def test_an_operation_the_api_refuses_reads_as_unreachable() -> None:
    # A route a weekly aMule bump renamed: /version answers 404 not_found.
    refused = ReadRejectedError("GET /api/v1/version: 404 not_found: no route")
    alerts = await _alerts(refused, refused, refused)
    assert alerts == [(120.0, _warning("amuled unreachable for 2 min"))]


@pytest.mark.asyncio
async def test_a_refused_password_escapes_its_turn() -> None:
    with pytest.raises(ClientAuthError):
        await _run(ClientAuthError("amuleapi refused the admin password"), _status(ed2k=_UP))


@pytest.mark.asyncio
async def test_unreachable_for_one_minute_never_alerts() -> None:
    assert await _alerts(_DOWN, _DOWN, _status(ed2k=_UP)) == []


@pytest.mark.asyncio
async def test_while_unreachable_only_the_api_alerts_and_the_channels_keep_their_readings() -> None:
    low = _status(ed2k=_LOW_ID)
    alerts = await _alerts(*[low] * 4, *[_DOWN] * 5, *[low] * 6)
    assert alerts == [  # the client's end held: 4 unanswered among its last 10 readings
        (360.0, _warning("amuled unreachable for 2 min")),
        (600.0, _warning(f"amuled ed2k: {_NOT_CONNECTABLE}")),
    ]


@pytest.mark.asyncio
async def test_each_reading_samples_every_channel_and_unreachable_makes_them_unknown() -> None:
    observability = await _run(_DOWN, _status(ed2k=_UP, kad=(False, None)), _DOWN)
    unknown = [
        LoggedLine(
            level="debug",
            message=f"status amuled {channel}: connected unknown, connectable unknown",
        )
        for channel in _CHANNELS
    ]
    assert observability.logger.lines == [
        LoggedLine(level="warning", message="amuled unreachable"),
        *unknown,
        LoggedLine(level="debug", message="status amuled ed2k: connected yes, connectable yes"),
        LoggedLine(level="debug", message="status amuled kad: connected no, connectable unknown"),
        LoggedLine(level="warning", message="amuled unreachable"),
        *unknown,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reading", "published"), [(_status(ed2k=_UP), _status(ed2k=_UP)), (_DOWN, None)]
)
async def test_each_reading_is_published_with_its_wall_and_monotonic_instants(
    *, reading: _Reading, published: ClientStatus | None
) -> None:
    fake_time = FakeTime()
    fake_time.step_wall(timedelta(hours=1))  # the two clocks part: each instant shows its clock
    status_reading_store = FakeStatusReadingStore((ClientName("amuled"),))
    sensor = _status_sensor(
        ClientName("amuled"),
        client=FakeStatusClient([_status(kad=_UP), reading]),
        fake_time=fake_time,
        observability=_Observability(fake_time),
        status_reading_writer=status_reading_store,
    )
    await _take_turns(sensor, turns=2)
    assert status_reading_store.read_readings() == {
        "amuled": PublishedReading(
            reading=StatusReading(read_at=fake_time.wall.now(), status=published),
            published_at=fake_time.monotonic.now(),
        )
    }


@pytest.mark.asyncio
async def test_a_wall_clock_step_forward_raises_no_alert_before_its_delay() -> None:
    # Degraded for four minutes of monotonic time, an hour and four minutes of wall clock.
    fake_time = FakeTime()
    observability = _Observability(fake_time)
    sensor = _status_sensor(
        ClientName("amuled"),
        client=FakeSteppedStatusClient([_status(ed2k=_LOW_ID)] * 5, fake_time=fake_time),
        fake_time=fake_time,
        observability=observability,
    )
    await _take_turns(sensor, turns=5)
    assert observability.notifier.notifications == []


def _sensor_over(fake_time: FakeTime, *readings: _Reading) -> StatusSensor:
    return _status_sensor(
        _AMULED,
        client=FakeStatusClient(list(readings)),
        fake_time=fake_time,
        observability=_Observability(fake_time),
    )


@pytest.mark.asyncio
async def test_the_first_turn_waits_nothing() -> None:
    fake_time = FakeTime()
    await _sensor_over(fake_time).wait_for_next_turn()
    assert fake_time.sleeps == []


@pytest.mark.asyncio
async def test_the_next_turn_waits_the_period_left_since_the_last_turn_ended() -> None:
    fake_time = FakeTime()
    sensor = _sensor_over(fake_time, _status(ed2k=_UP))
    await sensor.run_once()
    fake_time.advance(timedelta(seconds=20))
    await sensor.wait_for_next_turn()
    assert fake_time.sleeps == [timedelta(seconds=40)]


@pytest.mark.asyncio
async def test_a_turn_past_its_period_starts_the_next_at_once() -> None:
    fake_time = FakeTime()
    sensor = _sensor_over(fake_time, _status(ed2k=_UP))
    await sensor.run_once()
    fake_time.advance(timedelta(seconds=90))
    await sensor.wait_for_next_turn()
    assert fake_time.sleeps == []


@pytest.mark.asyncio
async def test_a_turn_that_raised_waits_a_full_period_too() -> None:
    fake_time = FakeTime()
    sensor = _sensor_over(fake_time, ClientAuthError("amuleapi refused the admin password"))
    with pytest.raises(ClientAuthError):
        await sensor.run_once()
    await sensor.wait_for_next_turn()
    assert fake_time.sleeps == [timedelta(seconds=60)]


def test_the_supervisor_names_the_work_after_its_client() -> None:
    fake_time = FakeTime()
    sensor = _status_sensor(
        _AMULED,
        client=FakeStatusClient([]),
        fake_time=fake_time,
        observability=_Observability(fake_time),
    )
    assert str(sensor) == "status reading of amuled"


def test_a_password_refused_while_the_node_runs_is_a_declared_outcome_each_turn(
    virtual_loop: VirtualLoop,
) -> None:
    refused = ClientAuthError("amuleapi refused the admin password")
    observability = _Observability(FakeTime())
    monotonic_clock = FakeLoopMonotonicClock(virtual_loop)
    sensor = StatusSensor(
        client_name=_AMULED,
        client=FakeStatusClient([refused] * 5),
        wall_clock=FakeLoopWallClock(virtual_loop),
        monotonic_clock=monotonic_clock,
        observability_dispatcher=observability.dispatcher,
        status_reading_writer=FakeStatusReadingStore((_AMULED,)),
        health_recorder=observability.health_recorder,
        client_component=client_component(_AMULED),
        channel_components={},
        download_tracking_component=None,
    )
    run_state, logger = FakeRunStateStore(), FakeLogger()
    virtual_loop.call_later(4 * 60.0 + 1.0, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=monotonic_clock,
        health_recorder=observability.health_recorder,
        logger=logger,
    )

    # Returns at the stop, no ``ExceptionGroup``: the node runs on.
    virtual_loop.run_until_complete(
        supervisor.supervise(
            [
                SupervisedWork(
                    work=sensor,
                    time_limit=timedelta(hours=1),
                    feeds=(status_sensor_component(_AMULED),),
                )
            ],
            arm_shutdown_bound=lambda: None,
        )
    )

    message = "status reading of amuled: amuleapi refused the admin password"
    assert logger.lines == [LoggedLine(level="warning", message=message)] * 5
