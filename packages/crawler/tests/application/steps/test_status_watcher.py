"""The status watcher: a reading every minute feeds the channel gauges and the health of the
client and of each channel, whose rules send today's alerts, boot included."""

import asyncio
from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.application.steps.node_health import HealthSubscriber, NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.application.steps.status_watcher import StatusWatcher
from p2pwatch.application.steps.supervisor import Supervisor
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.client_errors import ClientAuthError, ClientError, ReadRejectedError
from p2pwatch.domain.download.disk_space import download_tracking_dependency
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.notification_sends import NotificationService
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import (
    CLIENT_UNREACHABLE,
    ChannelStatus,
    ClientStatus,
    PublishedReading,
    StatusReading,
    channel_dependency,
    client_dependency,
)
from p2pwatch.domain.work_dependencies import status_reading_dependency
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_loop_monotonic_clock import FakeLoopMonotonicClock
from tests.fakes.adapters.driven.fake_loop_wall_clock import FakeLoopWallClock
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE
from tests.fakes.adapters.driven.fake_run_state_store import FakeRunStateStore
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_status_client import FakeStatusClient
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.composition.fake_restartable_builder import FakeRestartableBuilder
from tests.support.virtual_time import VirtualLoop

type _Reading = ClientStatus | ClientError

_UP = (True, True)
_LOW_ID = (True, False)  # on the network, not connectable
_DOWN = make_unreachable()
_NODE_ID = NodeId("titar-node-1")
_AMULED = ClientName("amuled")
_CHANNELS = (Channel("ed2k"), Channel("kad"))
_HOUR = timedelta(hours=1)


class _Observability:
    """The dispatch step over fakes, each notification left timed: an alert is one; each change
    of health also passed on to ``also``, after the alerts."""

    def __init__(self, fake_time: FakeTime, *, also: Sequence[HealthSubscriber] = ()) -> None:
        self.logger = FakeLogger()
        self._fake_time, self._start = fake_time, fake_time.monotonic.now()
        self.notifications: list[tuple[float, Notification]] = []
        self.dispatcher = ObservabilityDispatcher(
            logger=self.logger,
            node_metric_writer=FakeNodeMetricStore(),
            leave_notification=self._leave,
            services=ONE_SERVICE_PER_AUDIENCE,
        )
        alerter = HealthAlerter(
            observability_dispatcher=self.dispatcher, node_id=_NODE_ID, min_free_bytes=None
        )
        self.health_logger = FakeLogger()
        self.node_health = NodeHealth(logger=self.health_logger, subscribers=(alerter.send, *also))

    def _leave(
        self, notification: Notification, *, services: Sequence[NotificationService]
    ) -> None:
        """Keeps ``notification`` for each of ``services``, with the seconds elapsed on the
        monotonic clock."""
        elapsed = (self._fake_time.monotonic.now() - self._start).total_seconds()
        self.notifications.extend((elapsed, notification) for _ in services)


def _status(**channels: tuple[bool, bool | None]) -> ClientStatus:
    return ClientStatus(
        version="3.0.1",
        channels=tuple(
            ChannelStatus(channel=Channel(name), connected=on, connectable=connectable)
            for name, (on, connectable) in channels.items()
        ),
    )


def _status_watcher(
    client_name: ClientName,
    *,
    client: StatusClient,
    fake_time: FakeTime,
    observability: _Observability,
    status_reading_writer: StatusReadingWriter | None = None,
    channels: Sequence[Channel] = _CHANNELS,
    download_tracking: ExternalDependency | None = None,
) -> StatusWatcher:
    return StatusWatcher(
        client_name=client_name,
        client=client,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        observability_dispatcher=observability.dispatcher,
        status_reading_writer=status_reading_writer or FakeStatusReadingStore((client_name,)),
        node_health=observability.node_health,
        client_dependency=client_dependency(client_name),
        channel_dependencies={
            channel: channel_dependency(client_name=client_name, channel=channel)
            for channel in channels
        },
        download_tracking_dependency=download_tracking,
    )


async def _take_turns(watcher: StatusWatcher, *, turns: int) -> None:
    for _ in range(turns):
        await watcher.wait_for_next_turn()
        await watcher.run_once()


async def _run(
    *readings: _Reading,
    client: ClientName = _AMULED,
    channels: Sequence[Channel] = _CHANNELS,
    download_tracking: ExternalDependency | None = None,
) -> _Observability:
    fake_time = FakeTime()
    observability = _Observability(fake_time)
    watcher = _status_watcher(
        client,
        client=FakeStatusClient(list(readings)),
        fake_time=fake_time,
        observability=observability,
        channels=channels,
        download_tracking=download_tracking,
    )
    await _take_turns(watcher, turns=len(readings))
    return observability


async def _alerts(*readings: _Reading) -> list[tuple[float, Notification]]:
    return (await _run(*readings)).notifications


def _warning(message: str) -> RelayedLogLine:
    return RelayedLogLine(message=message, severity=Severity.WARNING, node_id=_NODE_ID)


def _info(message: str) -> RelayedLogLine:
    return RelayedLogLine(message=message, severity=Severity.INFO, node_id=_NODE_ID)


_NOT_CONNECTABLE = "not connectable for 5 min"


@pytest.mark.asyncio
async def test_not_connectable_from_the_first_reading_alerts_at_five_minutes_once() -> None:
    observability = await _run(*[_status(kad=_LOW_ID)] * 10)
    assert observability.notifications == [(300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}"))]
    assert (
        LoggedLine(
            level="warning", message="channel amuled kad, not connectable: unknown to failing"
        )
        in observability.health_logger.lines
    )


@pytest.mark.asyncio
async def test_a_channel_failing_for_four_minutes_never_alerts() -> None:
    alerts = await _alerts(*[_status(ed2k=_LOW_ID)] * 5, _status(ed2k=_UP))
    assert alerts == []


@pytest.mark.asyncio
async def test_off_the_network_alerts_whatever_the_client_and_channel() -> None:
    observability = await _run(
        *[_status(x=(False, None))] * 6, client=ClientName("fake"), channels=(Channel("x"),)
    )
    assert observability.notifications == [(300.0, _warning("fake x: off its network for 5 min"))]
    assert (
        LoggedLine(level="warning", message="channel fake x, not connected: unknown to failing")
        in observability.health_logger.lines
    )


@pytest.mark.asyncio
async def test_off_the_network_ends_at_the_ninth_reading_back_on_it() -> None:
    # It ends under 2 readings off among the channel's last 10: the eighth back on still sees two.
    alerts = await _alerts(*[_status(kad=(False, None))] * 6, *[_status(kad=_UP)] * 9)
    assert alerts == [
        (300.0, _warning("amuled kad: off its network for 5 min")),
        (840.0, _info("amuled kad: back on its network")),
    ]


@pytest.mark.asyncio
async def test_an_unreachable_reading_between_two_runs_off_the_network_ends_nothing() -> None:
    # The unknown reading records nothing: the channel stays failing, so no end, no second alert.
    off = _status(kad=(False, None))
    alerts = await _alerts(*[off] * 6, _DOWN, *[off] * 6)
    assert alerts == [(300.0, _warning("amuled kad: off its network for 5 min"))]


@pytest.mark.asyncio
async def test_not_connectable_ends_at_the_ninth_connectable_reading() -> None:
    # It ends under 2 readings not connectable among the channel's last 10.
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, *[_status(kad=_UP)] * 9)
    assert alerts == [
        (300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}")),
        (840.0, _info("amuled kad: connectable again")),
    ]


@pytest.mark.asyncio
async def test_an_unknown_connectable_field_between_two_runs_not_connectable_records_nothing() -> (
    None
):
    # aMule could not tell: the sixth reading not connectable is the seventh reading.
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 3, unknown, *[_status(kad=_LOW_ID)] * 3)
    assert alerts == [(360.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}"))]


@pytest.mark.asyncio
async def test_an_unknown_connectable_field_after_an_alert_ends_nothing() -> None:
    unknown = _status(kad=(True, None))
    alerts = await _alerts(*[_status(kad=_LOW_ID)] * 6, unknown, *[_status(kad=_UP)] * 9)
    assert alerts == [
        (300.0, _warning(f"amuled kad: {_NOT_CONNECTABLE}")),
        (900.0, _info("amuled kad: connectable again")),
    ]


@pytest.mark.asyncio
async def test_unreachable_alerts_at_two_minutes_and_ends_at_the_ninth_answer() -> None:
    # It ends under 2 unanswered among the last 10 readings: the eighth answer still sees two.
    observability = await _run(_DOWN, _DOWN, _DOWN, *[_status(ed2k=_UP)] * 9)
    assert observability.notifications == [
        (120.0, _warning("amuled unreachable for 2 min")),
        (660.0, _info("amuled reachable again")),
    ]
    assert (
        observability.logger.lines.count(LoggedLine(level="warning", message="amuled unreachable"))
        == 3
    )
    client_lines = [
        line for line in observability.health_logger.lines if line.message.startswith("client ")
    ]
    assert client_lines == [
        LoggedLine(level="warning", message="client amuled, unreachable: unknown to failing"),
        LoggedLine(level="info", message="client amuled, unreachable: failing to healthy"),
    ]


@pytest.mark.asyncio
async def test_an_operation_the_api_refuses_reads_as_unreachable() -> None:
    # A route a weekly aMule bump renamed: /version answers 404 not_found.
    refused = ReadRejectedError("GET /api/v1/version: 404 not_found: no route")
    alerts = await _alerts(refused, refused, refused)
    assert alerts == [(120.0, _warning("amuled unreachable for 2 min"))]


@pytest.mark.asyncio
async def test_a_refused_password_raises_out_of_the_turn() -> None:
    with pytest.raises(ClientAuthError):
        await _run(ClientAuthError("amuleapi refused the admin password"), _status(ed2k=_UP))


_NO_NETWORK = _status(ed2k=(False, None), kad=(False, None))


def _no_network_lines(observability: _Observability) -> list[LoggedLine]:
    """The log lines of each change of download tracking's health under "connected to no
    network"."""
    return [
        line
        for line in observability.health_logger.lines
        if ", connected to no network: " in line.message
    ]


@pytest.mark.asyncio
async def test_six_readings_on_no_network_fail_download_tracking_and_nine_on_one_heal_it() -> None:
    on_ed2k_alone = _status(ed2k=_UP, kad=(False, None))
    observability = await _run(
        *[_NO_NETWORK] * 6,
        *[on_ed2k_alone] * 9,
        download_tracking=download_tracking_dependency(_AMULED),
    )
    assert _no_network_lines(observability) == [
        LoggedLine(
            level="warning",
            message="download tracking amuled, connected to no network: unknown to failing",
        ),
        LoggedLine(
            level="info",
            message="download tracking amuled, connected to no network: failing to healthy",
        ),
    ]


@pytest.mark.asyncio
async def test_an_unreachable_reading_tells_nothing_of_the_client_s_networks() -> None:
    held = await _run(
        *[_NO_NETWORK] * 5, _DOWN, download_tracking=download_tracking_dependency(_AMULED)
    )
    failed = await _run(
        *[_NO_NETWORK] * 5,
        _DOWN,
        _NO_NETWORK,
        download_tracking=download_tracking_dependency(_AMULED),
    )

    # The sixth reading on no network is the seventh reading: aMule unreachable records nothing.
    assert _no_network_lines(held) == []
    assert _no_network_lines(failed) == [
        LoggedLine(
            level="warning",
            message="download tracking amuled, connected to no network: unknown to failing",
        )
    ]


@pytest.mark.asyncio
async def test_unreachable_for_one_minute_never_alerts() -> None:
    assert await _alerts(_DOWN, _DOWN, _status(ed2k=_UP)) == []


@pytest.mark.asyncio
async def test_while_unreachable_the_channels_keep_their_latest_readings() -> None:
    # The two readings after the outage complete the channel's six; the client's end is held:
    # 4 unanswered among its last 10 readings.
    low = _status(ed2k=_LOW_ID)
    alerts = await _alerts(*[low] * 4, *[_DOWN] * 5, *[low] * 6)
    assert alerts == [
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
    watcher = _status_watcher(
        ClientName("amuled"),
        client=FakeStatusClient([_status(kad=_UP), reading]),
        fake_time=fake_time,
        observability=_Observability(fake_time),
        status_reading_writer=status_reading_store,
    )
    await _take_turns(watcher, turns=2)
    assert status_reading_store.read_readings() == {
        "amuled": PublishedReading(
            reading=StatusReading(read_at=fake_time.wall.now(), status=published),
            published_at=fake_time.monotonic.now(),
        )
    }


def _watcher_over(fake_time: FakeTime, *readings: _Reading) -> StatusWatcher:
    return _status_watcher(
        _AMULED,
        client=FakeStatusClient(list(readings)),
        fake_time=fake_time,
        observability=_Observability(fake_time),
    )


@pytest.mark.asyncio
async def test_the_first_reading_waits_nothing() -> None:
    fake_time = FakeTime()
    await _watcher_over(fake_time).wait_for_next_turn()
    assert fake_time.sleeps == []


@pytest.mark.asyncio
async def test_the_next_reading_waits_what_is_left_of_the_minute_since_the_latest_one_ended() -> (
    None
):
    fake_time = FakeTime()
    watcher = _watcher_over(fake_time, _status(ed2k=_UP))
    await watcher.run_once()
    fake_time.advance(timedelta(seconds=20))
    await watcher.wait_for_next_turn()
    assert fake_time.sleeps == [timedelta(seconds=40)]


@pytest.mark.asyncio
async def test_a_minute_already_past_the_latest_reading_starts_the_next_at_once() -> None:
    fake_time = FakeTime()
    watcher = _watcher_over(fake_time, _status(ed2k=_UP))
    await watcher.run_once()
    fake_time.advance(timedelta(seconds=90))
    await watcher.wait_for_next_turn()
    assert fake_time.sleeps == []


@pytest.mark.asyncio
async def test_a_reading_that_raised_waits_a_full_minute_before_the_next() -> None:
    fake_time = FakeTime()
    watcher = _watcher_over(fake_time, ClientAuthError("amuleapi refused the admin password"))
    with pytest.raises(ClientAuthError):
        await watcher.run_once()
    await watcher.wait_for_next_turn()
    assert fake_time.sleeps == [timedelta(seconds=60)]


def test_a_password_refused_at_every_reading_fails_each_turn_and_the_node_runs_on(
    virtual_loop: VirtualLoop,
) -> None:
    refused = ClientAuthError("amuleapi refused the admin password")
    observability = _Observability(FakeTime())
    monotonic_clock = FakeLoopMonotonicClock(virtual_loop)
    watcher = StatusWatcher(
        client_name=_AMULED,
        client=FakeStatusClient([refused] * 5),
        wall_clock=FakeLoopWallClock(virtual_loop),
        monotonic_clock=monotonic_clock,
        observability_dispatcher=observability.dispatcher,
        status_reading_writer=FakeStatusReadingStore((_AMULED,)),
        node_health=observability.node_health,
        client_dependency=client_dependency(_AMULED),
        channel_dependencies={},
        download_tracking_dependency=None,
    )
    run_state, logger = FakeRunStateStore(), FakeLogger()
    virtual_loop.call_later(4 * 60.0 + 1.0, run_state.set_shutdown_requested)
    supervisor = Supervisor(
        run_state_reader=run_state,
        monotonic_clock=monotonic_clock,
        node_health=observability.node_health,
        logger=logger,
    )

    # Returns at the shutdown, with no exception: the node ran on.
    virtual_loop.run_until_complete(
        supervisor.supervise(
            [
                SupervisedWork(
                    work=watcher,
                    time_limit=timedelta(hours=1),
                    dependencies=(status_reading_dependency(_AMULED),),
                )
            ],
            arm_shutdown_bound=lambda: None,
        )
    )

    message = "status reading amuled: amuleapi refused the admin password"
    assert logger.lines == [LoggedLine(level="warning", message=message)] * 5
    # A refused password is an expected error: no turn met a bug.
    assert observability.health_logger.lines == [
        LoggedLine(level="info", message="status reading amuled, bugs: unknown to healthy")
    ]


def test_the_status_reading_is_named_after_its_client() -> None:
    assert str(_watcher_over(FakeTime())) == "status reading amuled"


class _KadSearchBug(Work):
    """A Kad search meeting a bug at every turn, its turns 200 s apart."""

    def __str__(self) -> str:
        return "search 'keroro' amuled kad"

    async def wait_for_next_turn(self) -> None:
        await asyncio.sleep(200.0)  # noqa: TID251

    async def run_once(self) -> None:
        raise KeyError("results")


class _RebuiltNode:
    """The status reading under the supervisor, beside a Kad search meeting a bug at each turn if
    ``kad_search_bug``; their parts are the aMule client's, whose rebuild hands back the status
    reading alone, over the same parts."""

    def __init__(self, loop: VirtualLoop, *readings: _Reading, kad_search_bug: bool) -> None:
        self._loop = loop
        self._client = FakeStatusClient(list(readings))
        self._monotonic_clock = FakeLoopMonotonicClock(loop)
        self.client_part = client_dependency(_AMULED)
        self._channel_parts = {
            channel: channel_dependency(client_name=_AMULED, channel=channel)
            for channel in _CHANNELS
        }
        self._status_reading_part = status_reading_dependency(_AMULED)
        self.observability = _Observability(FakeTime(), also=(self._to_policy,))
        self.amule_client = FakeRestartableBuilder(works_over=self._works_over)
        self._works = [self._status_reading()]
        if kad_search_bug:
            kad_part = self._channel_parts[Channel("kad")]
            bug = SupervisedWork(work=_KadSearchBug(), time_limit=_HOUR, dependencies=(kad_part,))
            self._works.append(bug)
        self._run_state = FakeRunStateStore()
        self._supervisor = Supervisor(
            run_state_reader=self._run_state,
            monotonic_clock=self._monotonic_clock,
            node_health=self.observability.node_health,
            logger=FakeLogger(),
        )
        self._policy = RestartPolicy(
            dependencies_of={
                self.amule_client: [self._status_reading_part, *self._channel_parts.values()]
            },
            works=self._works,
            restart=self._supervisor.restart,
            logger=FakeLogger(),
        )

    async def _to_policy(self, transition: HealthTransition) -> None:
        await self._policy(transition)

    def _works_over(self, _state: object, /) -> Sequence[SupervisedWork]:
        """The first works at the first build, the status reading alone at each rebuild."""
        return [self._status_reading()] if self.amule_client.built else self._works

    def _status_reading(self) -> SupervisedWork:
        watcher = StatusWatcher(
            client_name=_AMULED,
            client=self._client,
            wall_clock=FakeLoopWallClock(self._loop),
            monotonic_clock=self._monotonic_clock,
            observability_dispatcher=self.observability.dispatcher,
            status_reading_writer=FakeStatusReadingStore((_AMULED,)),
            node_health=self.observability.node_health,
            client_dependency=self.client_part,
            channel_dependencies=self._channel_parts,
            download_tracking_dependency=None,
        )
        return SupervisedWork(
            work=watcher, time_limit=_HOUR, dependencies=(self._status_reading_part,)
        )

    def run_for(self, seconds: float) -> None:
        self._loop.call_later(seconds, self._run_state.set_shutdown_requested)
        self._loop.run_until_complete(self._run())

    async def _run(self) -> None:
        works = await self._supervisor.build_first(self.amule_client)
        await self._supervisor.supervise(works, arm_shutdown_bound=lambda: None)


def test_amule_unreachable_fails_the_client_s_rule_and_rebuilds_nothing(
    virtual_loop: VirtualLoop,
) -> None:
    node = _RebuiltNode(virtual_loop, *[_DOWN] * 20, kad_search_bug=False)

    node.run_for(19 * 60.0 + 1.0)

    assert node.amule_client.rebuilds() == 0
    assert node.client_part.state(CLIENT_UNREACHABLE) is HealthState.FAILING


def test_a_rebuild_of_the_client_under_an_open_alert_neither_sends_it_again_nor_ends_it(
    virtual_loop: VirtualLoop,
) -> None:
    kad_off = _status(kad=(False, None))
    # The alert opens at the sixth reading, 300 s; the search's third bug rebuilds at 600 s.
    node = _RebuiltNode(virtual_loop, *[kad_off] * 30, kad_search_bug=True)

    node.run_for(600.0 + 7 * 60.0 + 1.0)  # eight readings after the rebuild, all off

    assert node.amule_client.built_at == [0.0, 600.0]
    notifications = node.observability.notifications
    assert [notification for _, notification in notifications] == [
        _warning("amuled kad: off its network for 5 min")
    ]
