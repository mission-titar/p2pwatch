"""The client's and its channels' alerts, sent when their health changes."""

from collections.abc import Mapping

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, NodeId
from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelField,
    ChannelRecovered,
    ClientReachableAgain,
    ClientUnreachableLasting,
    Event,
)
from p2pwatch.domain.status_reading import (
    CHANNEL_ALERT_AFTER,
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    UNREACHABLE_ALERT_AFTER,
)

# The field of the status reading each channel rule is about, as its alert names it.
_CHANNEL_FIELDS: Mapping[HealthRule, ChannelField] = {
    CHANNEL_NOT_CONNECTED: "connected",
    CHANNEL_NOT_CONNECTABLE: "connectable",
}


class HealthAlerter:
    """Sends the client's and its channels' alerts when their health changes, such as "amuled
    unreachable for 2 min" when it starts failing, "amuled reachable again" when it recovers."""

    def __init__(
        self, *, observability_dispatcher: ObservabilityDispatcher, node_id: NodeId
    ) -> None:
        self._observability_dispatcher = observability_dispatcher
        self._node_id = node_id

    async def send(self, transition: HealthTransition) -> None:
        if transition.current is HealthState.FAILING:
            alert = self._alert(transition)
        elif transition.previous is HealthState.FAILING:  # healthy from the start: none to end
            alert = self._end(transition)
        else:
            return
        if alert is not None:
            await self._observability_dispatcher.dispatch(alert)

    def _alert(self, transition: HealthTransition) -> Event | None:
        component, node_id = transition.component, self._node_id
        if transition.rule == CLIENT_UNREACHABLE:
            return ClientUnreachableLasting(
                client_name=component.client_name,
                unreachable_for_seconds=UNREACHABLE_ALERT_AFTER.total_seconds(),
                node_id=node_id,
            )
        if (field := _CHANNEL_FIELDS.get(transition.rule)) is not None:
            return ChannelDegraded(
                client_name=component.client_name,
                channel=_channel_of(transition),
                field=field,
                degraded_for_seconds=CHANNEL_ALERT_AFTER.total_seconds(),
                node_id=node_id,
            )
        return None

    def _end(self, transition: HealthTransition) -> Event | None:
        component, node_id = transition.component, self._node_id
        if transition.rule == CLIENT_UNREACHABLE:
            return ClientReachableAgain(client_name=component.client_name, node_id=node_id)
        if (field := _CHANNEL_FIELDS.get(transition.rule)) is not None:
            return ChannelRecovered(
                client_name=component.client_name,
                channel=_channel_of(transition),
                field=field,
                node_id=node_id,
            )
        return None


def _channel_of(transition: HealthTransition) -> Channel:
    channel = transition.component.channel
    if channel is None:
        raise ValueError(f"{transition.component.name}: no channel to name in its alert")
    return channel
