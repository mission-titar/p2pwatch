"""One client's status loop: a reading every minute feeds the channel gauges, and a degraded state
alerts once it has lasted, whatever came before it, boot included (spec stage 2, D15).

The alert timers live in memory, on the monotonic clock: a restart restarts them, so an ongoing
degradation alerts at most one delay later.
"""

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
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
from p2pwatch.ports.driven.client_errors import ClientAuthError, ClientError
from p2pwatch.ports.driven.client_status import StatusClient, StatusReading
from p2pwatch.ports.driven.clock import MonotonicClock, MonotonicInstant, WallClock
from p2pwatch.ports.driven.telemetry import Telemetry

STATUS_PERIOD = timedelta(minutes=1)
CHANNEL_ALERT_AFTER = timedelta(minutes=5)
UNREACHABLE_ALERT_AFTER = timedelta(minutes=2)
READING_FRESH_FOR = 2 * STATUS_PERIOD


class StatusBoard:
    """Each client's latest reading, published by its loop and read on the webui's thread (D21).
    Its age is measured on the monotonic clock: its ``read_at`` is for display."""

    def __init__(self, client_names: Iterable[str], monotonic_clock: MonotonicClock) -> None:
        self._monotonic_clock = monotonic_clock
        self._readings: Mapping[str, StatusReading | None] = dict.fromkeys(client_names)
        self._published_at_by_client_name: Mapping[str, MonotonicInstant] = {}

    def publish(self, client_name: str, reading: StatusReading) -> None:
        # New maps, never a mutation: the other thread reads whole snapshots, no lock needed. The
        # instant first, so a reader that sees a reading sees when it was published.
        self._published_at_by_client_name = {
            **self._published_at_by_client_name,
            client_name: self._monotonic_clock.now(),
        }
        self._readings = {**self._readings, client_name: reading}

    def readings(self) -> Mapping[str, StatusReading | None]:
        return self._readings

    def is_current(self, client_name: str) -> bool:
        published_at = self._published_at_by_client_name.get(client_name)
        if published_at is None:
            return False
        return self._monotonic_clock.now() - published_at <= READING_FRESH_FOR


@dataclass
class StatusLoopDeps:
    client_name: str  # as alerts and metrics label it
    client: StatusClient
    wall_clock: WallClock
    monotonic_clock: MonotonicClock
    telemetry: Telemetry
    shutdown: asyncio.Event
    board: StatusBoard


class _AlertTimer:
    """Since when one state reads degraded, and whether its alert has fired."""

    def __init__(self, delay: timedelta) -> None:
        self._delay = delay
        self._since: MonotonicInstant | None = None
        self._alerted = False

    def observe(
        self, healthy: bool | None, now: MonotonicInstant
    ) -> Literal["alert", "recovery"] | None:
        if healthy is None:  # unknown stops the timer; a recovery stays due until a healthy reading
            self._since = None
            return None
        if healthy:
            self._since = None
            recovered, self._alerted = self._alerted, False
            return "recovery" if recovered else None
        self._since = self._since or now
        if self._alerted or now - self._since < self._delay:
            return None
        self._alerted = True
        return "alert"


async def status_loop(deps: StatusLoopDeps) -> None:
    """Reads the status every period until shutdown."""
    api_timer = _AlertTimer(UNREACHABLE_ALERT_AFTER)
    channel_timers: dict[tuple[str, ChannelField], _AlertTimer] = {}

    async def _observe(
        timer: _AlertTimer, healthy: bool | None, alert: Event, recovery: Event
    ) -> None:
        change = timer.observe(healthy, deps.monotonic_clock.now())
        if change is not None:
            await deps.telemetry.emit(alert if change == "alert" else recovery)

    while not deps.shutdown.is_set():
        try:
            status = await deps.client.status()
        except ClientAuthError:
            raise  # a wrong password is config, not an outage
        except ClientError:  # a refused route too: a renamed /version must not end the crawler
            deps.board.publish(deps.client_name, StatusReading(deps.wall_clock.now(), None))
            await deps.telemetry.emit(ClientUnreachable(deps.client_name))
            # Every channel is unknown while the API is: only the API's own alert can fire.
            readings: list[tuple[str, bool | None, bool | None]] = [
                (channel, None, None) for channel in dict.fromkeys(c for c, _ in channel_timers)
            ]
            reachable = False
        else:
            deps.board.publish(deps.client_name, StatusReading(deps.wall_clock.now(), status))
            readings = [(c.channel, c.connected, c.connectable) for c in status.channels]
            reachable = True
        await _observe(
            api_timer,
            reachable,
            ClientUnreachableLasting(deps.client_name, UNREACHABLE_ALERT_AFTER.total_seconds()),
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
                    channel_timers.setdefault((channel, field), _AlertTimer(CHANNEL_ALERT_AFTER)),
                    healthy,
                    ChannelDegraded(
                        deps.client_name, channel, field, CHANNEL_ALERT_AFTER.total_seconds()
                    ),
                    ChannelRecovered(deps.client_name, channel, field),
                )
        await deps.monotonic_clock.sleep(STATUS_PERIOD)
