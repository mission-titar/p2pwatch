"""The client's, its channels' and the download disk's alerts, sent when their health
changes."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.download.disk_space import CONNECTED_TO_NO_NETWORK, DISK_SPACE_LOW
from p2pwatch.domain.health.component import Component, HealthTransition
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
# on a notification service's rule would be sent through that service.
_RULES_WITHOUT_AN_ALERT = frozenset({BUGS, SEARCHES_FAILED, CONNECTED_TO_NO_NETWORK, SENDS_FAILED})


@dataclass(kw_only=True, frozen=True)
class ClientAlert:
    """The client's part, and the client its alerts name: "amuled unreachable for 2 min"."""

    part: Component
    client_name: ClientName


@dataclass(kw_only=True, frozen=True)
class ChannelAlert:
    """A channel's part, and the client and channel its alerts name: "amuled kad: off its network
    for 5 min"."""

    part: Component
    client_name: ClientName
    channel: Channel


@dataclass(kw_only=True, frozen=True)
class DiskAlert:
    """Download tracking's part, and the floor its alert names: "download disk low: under the
    10.0 GiB floor (no new download)"."""

    part: Component
    min_free_bytes: int


class HealthAlerter:
    """Sends the alerts of the parts it is given, the client's, its channels' and the download
    disk's, when their health changes, such as "amuled unreachable for 2 min" when it starts
    failing."""

    def __init__(
        self,
        *,
        observability_dispatcher: ObservabilityDispatcher,
        node_id: NodeId,
        client: ClientAlert,
        channels: Sequence[ChannelAlert],
        disk: DiskAlert | None,
    ) -> None:
        self._observability_dispatcher = observability_dispatcher
        self._node_id = node_id
        self._client = client
        self._channels = {channel.part: channel for channel in channels}
        self._disk = disk  # None: the node downloads nothing

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
        rule, part, node_id = transition.rule, transition.component, self._node_id
        if rule == CLIENT_UNREACHABLE and part is self._client.part:
            return ClientUnreachableLasting(
                client_name=self._client.client_name,
                unreachable_for_seconds=UNREACHABLE_ALERT_AFTER.total_seconds(),
                node_id=node_id,
            )
        if (field := _CHANNEL_FIELDS.get(rule)) is not None and part in self._channels:
            channel = self._channels[part]
            return ChannelDegraded(
                client_name=channel.client_name,
                channel=channel.channel,
                field=field,
                degraded_for_seconds=CHANNEL_ALERT_AFTER.total_seconds(),
                node_id=node_id,
            )
        if rule == DISK_SPACE_LOW and self._disk is not None and part is self._disk.part:
            return DiskSpaceLow(min_free_bytes=self._disk.min_free_bytes, node_id=node_id)
        raise _no_alert_for(transition)

    def _end(self, transition: HealthTransition) -> Event | None:
        rule, part, node_id = transition.rule, transition.component, self._node_id
        if rule == CLIENT_UNREACHABLE and part is self._client.part:
            return ClientReachableAgain(client_name=self._client.client_name, node_id=node_id)
        if (field := _CHANNEL_FIELDS.get(rule)) is not None and part in self._channels:
            channel = self._channels[part]
            return ChannelRecovered(
                client_name=channel.client_name,
                channel=channel.channel,
                field=field,
                node_id=node_id,
            )
        if rule == DISK_SPACE_LOW and self._disk is not None and part is self._disk.part:
            return None  # the disk alert has no end, as it never had
        raise _no_alert_for(transition)


def _no_alert_for(transition: HealthTransition) -> ValueError:
    return ValueError(
        f"{transition.component.name}, {transition.rule.name}: no alert for this part under this"
        " rule"
    )
