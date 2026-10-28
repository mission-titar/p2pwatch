"""One client's status loop: a reading every minute feeds the channel gauges, and a degraded state
alerts once it has lasted, whatever came before it, boot included (spec stage 2, D15).

The alert timers live in memory, on the monotonic clock: a restart restarts them, so an ongoing
degradation alerts at most one delay later.
"""

from datetime import timedelta
from typing import Literal

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.client_errors import ClientAuthError, ClientError
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.monotonic_instant import MonotonicInstant
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
from p2pwatch.domain.status_reading import STATUS_PERIOD, ClientStatus, StatusReading

CHANNEL_ALERT_AFTER = timedelta(minutes=5)
UNREACHABLE_ALERT_AFTER = timedelta(minutes=2)


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


class StatusLoop:
    """One client's status loop; its alert timers are its own state."""

    def __init__(
        self,
        *,
        client_name: ClientName,
        client: StatusClient,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        observability_dispatcher: ObservabilityDispatcher,
        run_state_reader: RunStateReader,
        status_reading_writer: StatusReadingWriter,
    ) -> None:
        self._client_name = client_name  # as alerts and metrics label it
        self._client = client
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._observability_dispatcher = observability_dispatcher
        self._run_state_reader = run_state_reader
        self._status_reading_writer = status_reading_writer
        self._api_timer = _AlertTimer(UNREACHABLE_ALERT_AFTER)
        self._channel_timers: dict[tuple[Channel, ChannelField], _AlertTimer] = {}

    async def run(self, node_id: NodeId) -> None:
        """Reads the status every period until shutdown, its alerts carrying ``node_id``."""
        while not self._run_state_reader.is_shutdown_requested():
            try:
                status = await self._client.status()
            except ClientAuthError:
                raise  # a wrong password is config, not an outage
            except ClientError:  # a refused route too: a renamed /version must not end the crawler
                self._publish(None)
                await self._observability_dispatcher.dispatch(ClientUnreachable(self._client_name))
                # Every channel is unknown while the API is: only the API's own alert can fire.
                readings: list[tuple[Channel, bool | None, bool | None]] = [
                    (channel, None, None)
                    for channel in dict.fromkeys(c for c, _ in self._channel_timers)
                ]
                reachable = False
            else:
                self._publish(status)
                readings = [(c.channel, c.connected, c.connectable) for c in status.channels]
                reachable = True
            await self._observe(
                self._api_timer,
                reachable,
                ClientUnreachableLasting(
                    self._client_name, UNREACHABLE_ALERT_AFTER.total_seconds(), node_id
                ),
                ClientReachableAgain(self._client_name, node_id),
            )
            for channel, connected, connectable in readings:
                await self._observability_dispatcher.dispatch(
                    ChannelStatusSampled(self._client_name, channel, connected, connectable)
                )
                fields: tuple[tuple[ChannelField, bool | None], ...] = (
                    ("connected", connected),
                    ("connectable", connectable),
                )
                for field, healthy in fields:
                    await self._observe(
                        self._channel_timers.setdefault(
                            (channel, field), _AlertTimer(CHANNEL_ALERT_AFTER)
                        ),
                        healthy,
                        ChannelDegraded(
                            self._client_name,
                            channel,
                            field,
                            CHANNEL_ALERT_AFTER.total_seconds(),
                            node_id,
                        ),
                        ChannelRecovered(self._client_name, channel, field, node_id),
                    )
            await self._monotonic_clock.sleep(STATUS_PERIOD)

    def _publish(self, status: ClientStatus | None) -> None:
        reading = StatusReading(self._wall_clock.now(), status)
        self._status_reading_writer.set_reading(
            self._client_name, reading, self._monotonic_clock.now()
        )

    async def _observe(
        self, timer: _AlertTimer, healthy: bool | None, alert: Event, recovery: Event
    ) -> None:
        change = timer.observe(healthy, self._monotonic_clock.now())
        if change is not None:
            await self._observability_dispatcher.dispatch(alert if change == "alert" else recovery)
