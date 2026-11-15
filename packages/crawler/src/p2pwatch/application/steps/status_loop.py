"""One client's status loop: a reading every minute feeds the channel gauges and the health of
the client and of each channel, and a channel not connectable alerts once it has lasted.

An unknown field records nothing, so while aMule does not answer each channel keeps its health.
The connectable timers live in memory, on the monotonic clock: a restart restarts them, so an
ongoing degradation alerts at most one delay later.
"""

from collections.abc import Mapping
from datetime import timedelta
from typing import Literal

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.client_errors import ClientAuthError, ClientError
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelRecovered,
    ChannelStatusSampled,
    ClientUnreachable,
)
from p2pwatch.domain.status_reading import (
    CHANNEL_ALERT_AFTER,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    STATUS_PERIOD,
    ChannelStatus,
    ClientStatus,
    StatusReading,
)


class _AlertTimer:
    """Since when one state reads degraded, and whether its alert has fired."""

    def __init__(self, delay: timedelta) -> None:
        self._delay = delay
        self._since: MonotonicInstant | None = None
        self._alerted = False

    def observe(
        self, healthy: bool | None, *, now: MonotonicInstant
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
    """One client's status loop, reading each of ``channel_components``' channels; its connectable
    timers are its own state."""

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
        node_id: NodeId,
        node_health: NodeHealth,
        client_component: Component,
        channel_components: Mapping[Channel, Component],
    ) -> None:
        self._client_name = client_name  # as alerts and metrics label it
        self._client = client
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._observability_dispatcher = observability_dispatcher
        self._run_state_reader = run_state_reader
        self._status_reading_writer = status_reading_writer
        self._node_id = node_id
        self._node_health = node_health
        self._client_component = client_component
        self._channel_components = channel_components
        self._connectable_timers = {
            channel: _AlertTimer(CHANNEL_ALERT_AFTER) for channel in channel_components
        }

    async def run(self) -> None:
        """Reads the status every period until shutdown."""
        while not self._run_state_reader.is_shutdown_requested():
            status: ClientStatus | None
            try:
                status = await self._client.status()
            except ClientAuthError:
                raise  # a wrong password is config, not an outage
            except ClientError:  # a refused route too: a renamed /version must not end the crawler
                status = None
            self._publish(status)
            if status is None:
                await self._observability_dispatcher.dispatch(
                    ClientUnreachable(client_name=self._client_name)
                )
            await self._node_health.record(
                on=self._client_component, rule=CLIENT_UNREACHABLE, detected=status is None
            )
            # A channel the reading leaves out, every one while aMule does not answer, is unknown.
            channels = {c.channel: c for c in status.channels} if status else {}
            for channel, component in self._channel_components.items():
                await self._read_channel(channel, reading=channels.get(channel), on=component)
            await self._monotonic_clock.sleep(STATUS_PERIOD)

    def _publish(self, status: ClientStatus | None) -> None:
        reading = StatusReading(read_at=self._wall_clock.now(), status=status)
        self._status_reading_writer.set_reading(
            self._client_name, reading=reading, published_at=self._monotonic_clock.now()
        )

    async def _read_channel(
        self, channel: Channel, *, reading: ChannelStatus | None, on: Component
    ) -> None:
        connected = None if reading is None else reading.connected
        connectable = None if reading is None else reading.connectable
        await self._observability_dispatcher.dispatch(
            ChannelStatusSampled(
                client_name=self._client_name,
                channel=channel,
                connected=connected,
                connectable=connectable,
            )
        )
        if connected is not None:
            await self._node_health.record(
                on=on, rule=CHANNEL_NOT_CONNECTED, detected=not connected
            )
        change = self._connectable_timers[channel].observe(
            connectable, now=self._monotonic_clock.now()
        )
        if change == "alert":
            await self._observability_dispatcher.dispatch(
                ChannelDegraded(
                    client_name=self._client_name,
                    channel=channel,
                    field="connectable",
                    degraded_for_seconds=CHANNEL_ALERT_AFTER.total_seconds(),
                    node_id=self._node_id,
                )
            )
        elif change == "recovery":
            await self._observability_dispatcher.dispatch(
                ChannelRecovered(
                    client_name=self._client_name,
                    channel=channel,
                    field="connectable",
                    node_id=self._node_id,
                )
            )
