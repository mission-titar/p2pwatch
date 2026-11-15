"""The client's and its channels' alerts, sent when their health changes."""

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import Channel, NodeId
from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelRecovered,
    ClientReachableAgain,
    ClientUnreachableLasting,
    Event,
)
from p2pwatch.domain.status_reading import (
    CHANNEL_ALERT_AFTER,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    UNREACHABLE_ALERT_AFTER,
)


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
        if transition.rule == CHANNEL_NOT_CONNECTED:
            return ChannelDegraded(
                client_name=component.client_name,
                channel=_channel_of(transition),
                field="connected",
                degraded_for_seconds=CHANNEL_ALERT_AFTER.total_seconds(),
                node_id=node_id,
            )
        return None

    def _end(self, transition: HealthTransition) -> Event | None:
        component, node_id = transition.component, self._node_id
        if transition.rule == CLIENT_UNREACHABLE:
            return ClientReachableAgain(client_name=component.client_name, node_id=node_id)
        if transition.rule == CHANNEL_NOT_CONNECTED:
            return ChannelRecovered(
                client_name=component.client_name,
                channel=_channel_of(transition),
                field="connected",
                node_id=node_id,
            )
        return None


def _channel_of(transition: HealthTransition) -> Channel:
    channel = transition.component.channel
    if channel is None:
        raise ValueError(f"{transition.component.name}: no channel to name in its alert")
    return channel
