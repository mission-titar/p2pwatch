"""The client's, its channels' and the download disk's alerts, sent when their health
changes."""

from collections.abc import Mapping

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.disk_space import CONNECTED_TO_NO_NETWORK, DISK_SPACE_LOW
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, NodeId
from p2pwatch.domain.observability.events import (
    ChannelDegraded,
    ChannelField,
    ChannelRecovered,
    ClientReachableAgain,
    ClientUnreachableLasting,
    DiskSpaceLow,
    Event,
)
from p2pwatch.domain.observability.notification_sends import SENDS_FAILED
from p2pwatch.domain.status_reading import (
    CHANNEL_ALERT_AFTER,
    CHANNEL_NOT_CONNECTABLE,
    CHANNEL_NOT_CONNECTED,
    CLIENT_UNREACHABLE,
    SEARCHES_FAILED,
    UNREACHABLE_ALERT_AFTER,
)
from p2pwatch.domain.work_components import BUGS

# The field of the status reading each channel rule is about, as its alert names it.
_CHANNEL_FIELDS: Mapping[HealthRule, ChannelField] = {
    CHANNEL_NOT_CONNECTED: "connected",
    CHANNEL_NOT_CONNECTABLE: "connectable",
}

# A part failing or healthy again under these rules has no alert: its log line tells it. An alert
# about the notifier would be sent through the notifier, whose send it records on the notifier.
_RULES_WITHOUT_AN_ALERT = frozenset({BUGS, SEARCHES_FAILED, CONNECTED_TO_NO_NETWORK, SENDS_FAILED})


class HealthAlerter:
    """Sends the client's, its channels' and the download disk's alerts when their health changes,
    such as "amuled unreachable for 2 min" when it starts failing."""

    def __init__(
        self,
        *,
        observability_dispatcher: ObservabilityDispatcher,
        node_id: NodeId,
        min_free_bytes: int | None,
    ) -> None:
        self._observability_dispatcher = observability_dispatcher
        self._node_id = node_id
        self._min_free_bytes = min_free_bytes  # the download disk's floor; None: no download

    async def send(self, transition: HealthTransition) -> None:
        alert: Event | None
        if transition.rule in _RULES_WITHOUT_AN_ALERT:
            return
        if transition.current is HealthState.FAILING:
            alert = self._alert(transition)
        elif transition.previous is HealthState.FAILING:  # healthy from the start: none to end
            alert = self._end(transition)
        else:
            return
        if alert is not None:
            await self._observability_dispatcher.dispatch_shielded(alert)

    def _alert(self, transition: HealthTransition) -> Event:
        node_id = self._node_id
        if transition.rule == CLIENT_UNREACHABLE:
            return ClientUnreachableLasting(
                client_name=_client_of(transition),
                unreachable_for_seconds=UNREACHABLE_ALERT_AFTER.total_seconds(),
                node_id=node_id,
            )
        if (field := _CHANNEL_FIELDS.get(transition.rule)) is not None:
            return ChannelDegraded(
                client_name=_client_of(transition),
                channel=_channel_of(transition),
                field=field,
                degraded_for_seconds=CHANNEL_ALERT_AFTER.total_seconds(),
                node_id=node_id,
            )
        if transition.rule == DISK_SPACE_LOW:
            return DiskSpaceLow(min_free_bytes=self._floor_of(transition), node_id=node_id)
        raise _no_alert_for(transition)

    def _floor_of(self, transition: HealthTransition) -> int:
        if self._min_free_bytes is None:
            raise ValueError(f"{transition.component.name}: no disk floor for its alert")
        return self._min_free_bytes

    def _end(self, transition: HealthTransition) -> Event | None:
        node_id = self._node_id
        if transition.rule == CLIENT_UNREACHABLE:
            return ClientReachableAgain(client_name=_client_of(transition), node_id=node_id)
        if (field := _CHANNEL_FIELDS.get(transition.rule)) is not None:
            return ChannelRecovered(
                client_name=_client_of(transition),
                channel=_channel_of(transition),
                field=field,
                node_id=node_id,
            )
        if transition.rule == DISK_SPACE_LOW:
            return None  # the disk alert has no end, as it never had
        raise _no_alert_for(transition)


def _no_alert_for(transition: HealthTransition) -> ValueError:
    return ValueError(
        f"{transition.component.name}, {transition.rule.name}: no alert for this rule"
    )


def _client_of(transition: HealthTransition) -> ClientName:
    client_name = transition.component.client_name
    if client_name is None:
        raise ValueError(f"{transition.component.name}: no client to name in its alert")
    return client_name


def _channel_of(transition: HealthTransition) -> Channel:
    channel = transition.component.channel
    if channel is None:
        raise ValueError(f"{transition.component.name}: no channel to name in its alert")
    return channel
