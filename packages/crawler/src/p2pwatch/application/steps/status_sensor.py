"""One client's status sensor, a work: a reading every minute feeds the channel gauges, the client's
unreachable condition and each channel's two fields' conditions, whose transitions alert (spec
stage 2, D15; v5 lot 4, D21).

An unknown field records nothing: while the API does not answer, each channel's conditions keep the
readings they held.
"""

from collections.abc import Mapping
from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.status_client import StatusClient
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.application.ports.driven.wall_clock import WallClock
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.client_errors import ClientAuthError, ClientError
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.outcome import Outcome, OutcomeSource
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.observability.events import ChannelStatusSampled, ClientUnreachable
from p2pwatch.domain.status_reading import (
    STATUS_API_ANSWER,
    STATUS_CONNECTABLE_FIELD,
    STATUS_CONNECTED_FIELD,
    STATUS_PERIOD,
    ChannelNotConnectable,
    ChannelNotConnected,
    ChannelStatus,
    ClientNotAnswering,
    ClientStatus,
    StatusReading,
)


class StatusSensor(Work):
    """One client's status sensor, recording each reading on the client's and its channels'
    components."""

    def __init__(
        self,
        *,
        client_name: ClientName,
        client: StatusClient,
        wall_clock: WallClock,
        monotonic_clock: MonotonicClock,
        observability_dispatcher: ObservabilityDispatcher,
        status_reading_writer: StatusReadingWriter,
        health_recorder: HealthRecorder,
        client_component: Component,
        channel_components: Mapping[Channel, Component],
    ) -> None:
        self._client_name = client_name  # as alerts and metrics label it
        self._client = client
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._observability_dispatcher = observability_dispatcher
        self._status_reading_writer = status_reading_writer
        self._health_recorder = health_recorder
        self._client_component = client_component
        self._channel_components = channel_components
        self._last_turn_ended_at: MonotonicInstant | None = None

    async def wait_for_next_turn(self) -> None:
        """Waits the period left since the last turn ended, nothing before the first."""
        if self._last_turn_ended_at is None:
            return
        left = STATUS_PERIOD - (self._monotonic_clock.now() - self._last_turn_ended_at)
        if left > timedelta(0):
            await self._monotonic_clock.sleep(left)

    async def run_once(self) -> None:
        """Reads the status once and records it on the client's and its channels' components."""
        try:
            await self._read()
        finally:  # a turn that raised still paces the next one
            self._last_turn_ended_at = self._monotonic_clock.now()

    async def _read(self) -> None:
        try:
            status = await self._client.status()
        except ClientAuthError:
            raise  # a wrong password is config, not an outage
        except ClientError:  # a refused route too: a renamed /version must not end the crawler
            self._publish(None)
            await self._observability_dispatcher.dispatch(
                ClientUnreachable(client_name=self._client_name)
            )
            channels: dict[Channel, ChannelStatus] = {}
            answer = Outcome.declared(ClientNotAnswering())
        else:
            self._publish(status)
            channels = {c.channel: c for c in status.channels}
            answer = Outcome.success()
        await self._health_recorder.record(answer, on=self._client_component, by=STATUS_API_ANSWER)
        for channel, component in self._channel_components.items():
            await self._read_channel(channel, reading=channels.get(channel), on=component)

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
        fields: tuple[tuple[bool | None, type[DeclaredFailure], OutcomeSource], ...] = (
            (connected, ChannelNotConnected, STATUS_CONNECTED_FIELD),
            (connectable, ChannelNotConnectable, STATUS_CONNECTABLE_FIELD),
        )
        for healthy, reason, source in fields:
            if healthy is not None:
                outcome = Outcome.success() if healthy else Outcome.declared(reason())
                await self._health_recorder.record(outcome, on=on, by=source)
