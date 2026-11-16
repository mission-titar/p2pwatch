"""Reads one client's status every minute: each reading feeds the channel gauges and the health
of the client, of each channel and of download tracking, which needs a channel connected.

A field aMule did not give records nothing, so while aMule does not answer each channel and
download tracking keep their health.
"""

from collections.abc import Mapping
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.client_errors import ClientAuthError, ClientError
from p2pwatch.domain.download.disk_space import CONNECTED_TO_NO_NETWORK
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import ChannelStatusSampled, ClientUnreachable
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    STATUS_PERIOD,
    ChannelStatus,
    ClientStatus,
    StatusReading,
)


class StatusWatcher(Work):
    """Reads one client's status every minute, a minute from the end of one reading to the start
    of the next, each of ``channel_components``' channels in it, and whether any is connected."""

    def __init__(
        self,
        *,
        client_name: ClientName,
        client: StatusClient,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        observability_dispatcher: ObservabilityDispatcher,
        status_reading_writer: StatusReadingWriter,
        node_health: NodeHealth,
        client_component: Component,
        channel_components: Mapping[Channel, Component],
        download_tracking_component: Component | None,
    ) -> None:
        self._client_name = client_name  # as alerts and metrics label it
        self._client = client
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._observability_dispatcher = observability_dispatcher
        self._status_reading_writer = status_reading_writer
        self._node_health = node_health
        self._client_component = client_component
        self._channel_components = channel_components
        self._download_tracking_component = download_tracking_component  # None: no download
        self._latest_reading_ended_at: MonotonicInstant | None = None

    def __str__(self) -> str:
        return f"status reading {self._client_name}"

    async def wait_for_next_turn(self) -> None:
        """Waits until a minute has passed since the latest reading ended; the first one waits
        nothing."""
        if self._latest_reading_ended_at is None:
            return
        left = STATUS_PERIOD - (self._monotonic_clock.now() - self._latest_reading_ended_at)
        if left > timedelta(0):
            await self._monotonic_clock.sleep(left)

    async def run_once(self) -> None:
        """Reads the status once, publishes it and records the health it shows."""
        try:
            await self._read()
        finally:  # a reading that raised, a refused password included, spaces the next one too
            self._latest_reading_ended_at = self._monotonic_clock.now()

    async def _read(self) -> None:
        status: ClientStatus | None
        try:
            status = await self._client.status()
        except ClientAuthError:
            raise  # a wrong password is configuration, not an outage: logged at each turn
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
        if status is not None and self._download_tracking_component is not None:
            on_a_network = any(channel.connected for channel in status.channels)
            await self._node_health.record(
                on=self._download_tracking_component,
                rule=CONNECTED_TO_NO_NETWORK,
                detected=not on_a_network,
            )

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
        if connectable is not None:
            await self._node_health.record(
                on=on, rule=CHANNEL_NOT_CONNECTABLE, detected=not connectable
            )
