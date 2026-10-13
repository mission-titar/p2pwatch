"""One client's status loop: a reading every minute feeds the channel gauges, and a degraded state
alerts once it has lasted, whatever came before it, boot included (spec stage 2, D15).

The alert timers live in memory: a restart restarts them, so an ongoing degradation alerts at most
one delay later.
"""

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelField,
    ChannelRecovered,
    ChannelStatusSampled,
    ClientReachableAgain,
    ClientUnreachable,
    ClientUnreachableLasting,
    Event,
)
from p2pwatch.ports.client_errors import ClientAuthError, ClientError
from p2pwatch.ports.client_status import StatusClient, StatusReading
from p2pwatch.ports.clock import Clock
from p2pwatch.ports.telemetry import Telemetry

STATUS_PERIOD_SECONDS = 60.0
CHANNEL_ALERT_AFTER_SECONDS = 300.0
UNREACHABLE_ALERT_AFTER_SECONDS = 120.0
READING_FRESH_FOR_SECONDS = 2 * STATUS_PERIOD_SECONDS


class StatusBoard:
    """Each client's latest reading, published by its loop and read on the webui's thread (D21)."""

    def __init__(self, client_names: Iterable[str], clock: Clock) -> None:
        self._clock = clock
        self._readings: Mapping[str, StatusReading | None] = dict.fromkeys(client_names)

    def publish(self, client_name: str, reading: StatusReading) -> None:
        # A new map, never a mutation: the other thread reads one whole snapshot, no lock needed.
        self._readings = {**self._readings, client_name: reading}

    def readings(self) -> Mapping[str, StatusReading | None]:
        return self._readings

    def is_current(self, reading: StatusReading) -> bool:
        return (self._clock.now() - reading.read_at).total_seconds() <= READING_FRESH_FOR_SECONDS


@dataclass
class StatusLoopDeps:
    client_name: str  # as alerts and metrics label it
    client: StatusClient
    clock: Clock
    telemetry: Telemetry
    shutdown: asyncio.Event
    board: StatusBoard


class _AlertTimer:
    """Since when one state reads degraded, and whether its alert has fired."""

    def __init__(self, delay_seconds: float) -> None:
        self._delay = delay_seconds
        self._since: datetime | None = None
        self._alerted = False

    def observe(self, healthy: bool | None, now: datetime) -> Literal["alert", "recovery"] | None:
        if healthy is None:  # unknown stops the timer; a recovery stays due until a healthy reading
            self._since = None
            return None
        if healthy:
            self._since = None
            recovered, self._alerted = self._alerted, False
            return "recovery" if recovered else None
        self._since = self._since or now
        if self._alerted or (now - self._since).total_seconds() < self._delay:
            return None
        self._alerted = True
        return "alert"


async def status_loop(deps: StatusLoopDeps) -> None:
    """Reads the status every period until shutdown."""
    api_timer = _AlertTimer(UNREACHABLE_ALERT_AFTER_SECONDS)
    channel_timers: dict[tuple[str, ChannelField], _AlertTimer] = {}

    async def _observe(
        timer: _AlertTimer, healthy: bool | None, alert: Event, recovery: Event
    ) -> None:
        change = timer.observe(healthy, deps.clock.now())
        if change is not None:
            await deps.telemetry.emit(alert if change == "alert" else recovery)

    while not deps.shutdown.is_set():
        try:
            await deps.client.connect()  # nothing else may connect a shared session (a pause)
            status = await deps.client.status()
        except ClientAuthError:
            raise  # a wrong password is config, not an outage
        except ClientError:  # a refused route too: a renamed /version must not end the crawler
            deps.board.publish(deps.client_name, StatusReading(deps.clock.now(), None))
            await deps.telemetry.emit(ClientUnreachable(deps.client_name))
            # Every channel is unknown while the API is: only the API's own alert can fire.
            readings: list[tuple[str, bool | None, bool | None]] = [
                (channel, None, None) for channel in dict.fromkeys(c for c, _ in channel_timers)
            ]
            reachable = False
        else:
            deps.board.publish(deps.client_name, StatusReading(deps.clock.now(), status))
            readings = [(c.channel, c.connected, c.connectable) for c in status.channels]
            reachable = True
        await _observe(
            api_timer,
            reachable,
            ClientUnreachableLasting(deps.client_name, UNREACHABLE_ALERT_AFTER_SECONDS),
            ClientReachableAgain(deps.client_name),
        )
        for channel, connected, connectable in readings:
            await deps.telemetry.emit(
                ChannelStatusSampled(deps.client_name, channel, connected, connectable)
            )
            fields: tuple[tuple[ChannelField, bool | None], ...] = (
                ("connected", connected),
                ("connectable", connectable),
            )
            for field, healthy in fields:
                await _observe(
                    channel_timers.setdefault(
                        (channel, field), _AlertTimer(CHANNEL_ALERT_AFTER_SECONDS)
                    ),
                    healthy,
                    ChannelDegraded(deps.client_name, channel, field, CHANNEL_ALERT_AFTER_SECONDS),
                    ChannelRecovered(deps.client_name, channel, field),
                )
        await deps.clock.sleep(STATUS_PERIOD_SECONDS)
