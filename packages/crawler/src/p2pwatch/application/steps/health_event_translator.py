"""The health event translator: the readings' transitions become today's connectivity events, an
alert on entering a condition's band, its end only on a return to healthy after it (spec v5 lot 4,
D21)."""

from collections.abc import Mapping

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.health.health_condition import HealthCondition
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelField,
    ChannelRecovered,
    ClientReachableAgain,
    ClientUnreachableLasting,
    Event,
)
from p2pwatch.domain.status_reading import (
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    lasting_at_entry,
)

_CHANNEL_FIELDS: Mapping[HealthCondition, ChannelField] = {
    CHANNEL_NOT_CONNECTED: "connected",
    CHANNEL_NOT_CONNECTABLE: "connectable",
}


class HealthEventTranslator:
    """A subscriber of the health recorder, dispatching the events the transitions stand for."""

    def __init__(
        self, *, observability_dispatcher: ObservabilityDispatcher, node_id: NodeId
    ) -> None:
        self._observability_dispatcher = observability_dispatcher
        self._node_id = node_id

    async def translate(self, transition: HealthTransition) -> None:
        event = self._event(transition)
        if event is not None:
            await self._observability_dispatcher.dispatch(event)

    def _event(self, transition: HealthTransition) -> Event | None:
        condition, labels = transition.condition, transition.component.labels
        band, _ = condition.band()
        if transition.current is band:
            alerts = True
        elif transition.previous is band:  # unknown to healthy ends no alert
            alerts = False
        else:
            return None
        if condition == CLIENT_UNREACHABLE:
            if alerts:
                return ClientUnreachableLasting(
                    client_name=labels.client_name,
                    unreachable_for_seconds=lasting_at_entry(condition).total_seconds(),
                    node_id=self._node_id,
                )
            return ClientReachableAgain(client_name=labels.client_name, node_id=self._node_id)
        field, channel = _CHANNEL_FIELDS.get(condition), labels.channel
        if field is None or channel is None:
            return None
        if alerts:
            return ChannelDegraded(
                client_name=labels.client_name,
                channel=channel,
                field=field,
                degraded_for_seconds=lasting_at_entry(condition).total_seconds(),
                node_id=self._node_id,
            )
        return ChannelRecovered(
            client_name=labels.client_name, channel=channel, field=field, node_id=self._node_id
        )
