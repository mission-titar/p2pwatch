"""Every health alert as the operator gets it: its log line, its severity, its notification, and
the reading it starts and ends at, from the status readings and the free-space readings."""

from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Protocol

import pytest

from p2pwatch.application.steps.download_cycle import DownloadCycle
from p2pwatch.application.steps.health_alerter import HealthAlerter
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.status_watcher import StatusWatcher
from p2pwatch.domain.client_errors import ClientError
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.notification import Notification, RelayedLogLine
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from p2pwatch.domain.status_reading import (
    ChannelStatus,
    ClientStatus,
    channel_dependency,
    client_dependency,
)
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_search_client import make_unreachable
from tests.fakes.adapters.driven.fake_status_client import FakeStatusClient
from tests.fakes.adapters.driven.fake_status_reading_store import FakeStatusReadingStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_cycle import NODE_ID, build_cycle
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

pytestmark = pytest.mark.asyncio

_AMULED = ClientName("amuled")
_CHANNELS = (Channel("ed2k"), Channel("kad"))
_GIB = 2**30
_FLOOR = 10 * _GIB

type _StatusReading = ClientStatus | ClientError


@dataclass(kw_only=True, frozen=True)
class _Alert:
    reading: int  # the reading it is sent at, the first one 1
    lines: tuple[LoggedLine, ...]  # the lines of that reading carrying its text
    sent: tuple[Audience, Notification]


def _warning(message: str, *, at: int) -> _Alert:
    return _Alert(
        reading=at,
        lines=(LoggedLine(level="warning", message=message),),
        sent=(
            Audience.OPERATIONS,
            RelayedLogLine(message=message, severity=Severity.WARNING, node_id=NODE_ID),
        ),
    )


def _info(message: str, *, at: int) -> _Alert:
    return _Alert(
        reading=at,
        lines=(LoggedLine(level="info", message=message),),
        sent=(
            Audience.OPERATIONS,
            RelayedLogLine(message=message, severity=Severity.INFO, node_id=NODE_ID),
        ),
    )


def _status(*, ed2k: tuple[bool, bool | None], kad: tuple[bool, bool | None]) -> ClientStatus:
    return ClientStatus(
        version="3.0.1",
        channels=(
            ChannelStatus(channel=Channel("ed2k"), connected=ed2k[0], connectable=ed2k[1]),
            ChannelStatus(channel=Channel("kad"), connected=kad[0], connectable=kad[1]),
        ),
    )


_UP = (True, True)
_OFF = (False, None)  # off its network, so aMule cannot tell whether it is connectable
_LOW_ID = (True, False)
_ALL_UP = _status(ed2k=_UP, kad=_UP)


# One reading the node takes, such as a status reading.
class _Reading(Protocol):
    def __call__(self) -> Awaitable[None]: ...


async def _alerts(
    readings: Sequence[_Reading], *, observability: ObservabilityOverFakes
) -> list[_Alert]:
    """Takes each reading in turn and keeps each notification sent at it."""
    alerts: list[_Alert] = []
    for number, take_reading in enumerate(readings, start=1):
        lines_before = len(observability.logger.lines)
        sent_before = len(observability.notifications)
        await take_reading()
        lines = observability.logger.lines[lines_before:]
        alerts += [
            _Alert(
                reading=number,
                lines=tuple(line for line in lines if line.message == _text_of(notification)),
                sent=(audience, notification),
            )
            for audience, notification in observability.notifications[sent_before:]
        ]
    return alerts


def _text_of(notification: Notification) -> str | None:
    return notification.message if isinstance(notification, RelayedLogLine) else None


async def _status_alerts(*readings: _StatusReading) -> list[_Alert]:
    observability, fake_time = ObservabilityOverFakes(), FakeTime()
    alerter = HealthAlerter(
        observability_dispatcher=observability.dispatcher, node_id=NODE_ID, min_free_bytes=_FLOOR
    )
    watcher = StatusWatcher(
        client_name=_AMULED,
        client=FakeStatusClient(list(readings)),
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        observability_dispatcher=observability.dispatcher,
        status_reading_writer=FakeStatusReadingStore((_AMULED,)),
        node_health=NodeHealth(logger=FakeLogger(), subscribers=(alerter.send,)),
        client_dependency=client_dependency(_AMULED),
        channel_dependencies={
            channel: channel_dependency(client_name=_AMULED, channel=channel)
            for channel in _CHANNELS
        },
    )
    return await _alerts([watcher.run_once] * len(readings), observability=observability)


async def _read_free_space(free: int, *, meter: FakeFreeSpaceMeter, cycle: DownloadCycle) -> None:
    meter.free = free
    await cycle.run_once()


async def _disk_alerts(*free_readings: int) -> list[_Alert]:
    observability, meter = ObservabilityOverFakes(), FakeFreeSpaceMeter(free_readings[0])
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        free_space_meter=meter,
        min_free=_FLOOR,
        observability_dispatcher=observability.dispatcher,
    )
    readings = [partial(_read_free_space, free, meter=meter, cycle=cycle) for free in free_readings]
    return await _alerts(readings, observability=observability)


@pytest.mark.parametrize(
    ("readings", "alerts"),
    [
        pytest.param(
            [make_unreachable()] * 3 + [_ALL_UP] * 9,
            [
                _warning("amuled unreachable for 2 min", at=3),
                _info("amuled reachable again", at=12),
            ],
            id="amuled unreachable",
        ),
        pytest.param(
            [_status(ed2k=_OFF, kad=_UP)] * 6 + [_ALL_UP] * 9,
            [
                _warning("amuled ed2k: off its network for 5 min", at=6),
                _info("amuled ed2k: back on its network", at=15),
            ],
            id="ed2k off its network",
        ),
        pytest.param(
            [_status(ed2k=_UP, kad=_OFF)] * 6 + [_ALL_UP] * 9,
            [
                _warning("amuled kad: off its network for 5 min", at=6),
                _info("amuled kad: back on its network", at=15),
            ],
            id="kad off its network",
        ),
        pytest.param(
            [_status(ed2k=_LOW_ID, kad=_UP)] * 6 + [_ALL_UP] * 9,
            [
                _warning("amuled ed2k: not connectable for 5 min", at=6),
                _info("amuled ed2k: connectable again", at=15),
            ],
            id="ed2k not connectable",
        ),
        pytest.param(
            [_status(ed2k=_UP, kad=_LOW_ID)] * 6 + [_ALL_UP] * 9,
            [
                _warning("amuled kad: not connectable for 5 min", at=6),
                _info("amuled kad: connectable again", at=15),
            ],
            id="kad not connectable",
        ),
        pytest.param([_ALL_UP] * 15, [], id="healthy from the first reading"),
    ],
)
async def test_each_status_alert_starts_and_ends_at_its_reading(
    *, readings: list[_StatusReading], alerts: list[_Alert]
) -> None:
    assert await _status_alerts(*readings) == alerts


async def test_the_disk_alert_starts_at_each_dip_under_its_floor_and_has_no_end() -> None:
    # Two dips, one reading exactly at the floor between them.
    alerts = await _disk_alerts(5 * _GIB, 4 * _GIB, _FLOOR, _FLOOR - 1)
    disk_low = "download disk low: under the 10.0 GiB floor (no new download)"
    assert alerts == [_warning(disk_low, at=1), _warning(disk_low, at=4)]
