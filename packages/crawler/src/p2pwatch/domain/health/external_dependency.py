"""What the node depends on and does not control, its health tracked, each rule with the alert it
sends and its end."""

from collections.abc import Mapping
from dataclasses import dataclass

from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.events import Event


@dataclass(kw_only=True, frozen=True)
class HealthAlert:
    """The alert a rule of a part sends when it turns failing, and its end when it turns healthy
    again, such as Kad's "off its network for 5 min", then "back on its network"."""

    when_failing: Event
    when_healthy_again: Event


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """A change of one part's state under one rule, such as the aMule client going from healthy to
    failing, with that rule's alert."""

    alert: HealthAlert
    previous: HealthState
    current: HealthState

    def alert_event(self) -> Event | None:
        """What its rule's alert sends at this change: the alert turning failing, its end turning
        healthy from failing, nothing healthy from the start."""
        if self.current is HealthState.FAILING:
            return self.alert.when_failing
        if self.previous is HealthState.FAILING:
            return self.alert.when_healthy_again
        return None


class ExternalDependency:
    """Something the node depends on and does not control, its health tracked, such as the aMule
    client or its Kad channel."""

    def __init__(
        self,
        *,
        name: str,
        client_name: ClientName | None,
        channel: Channel | None = None,
        rules: Mapping[HealthRule, HealthAlert],
    ) -> None:
        self.name = name  # "client amuled", as the log names it
        self.client_name = client_name  # "amuled"; None for the disk, the services, local.db
        self.channel = channel  # "kad" for a part of one channel
        self._alerts = dict(rules)
        self._latest_detected: dict[HealthRule, tuple[bool, ...]] = dict.fromkeys(rules, ())
        self._states = dict.fromkeys(rules, HealthState.UNKNOWN)

    def record(self, *, rule: HealthRule, detected: bool) -> HealthTransition | None:
        """Counts one check of ``rule``, ``detected`` whether it saw its case; returns the change of
        state it caused, if any."""
        latest_detected = (*self._latest_detected[rule], detected)[-rule.checks_kept :]
        previous = self._states[rule]
        current = rule.state_after(latest_detected, previous=previous)
        self._latest_detected[rule], self._states[rule] = latest_detected, current
        if current is previous:
            return None
        return HealthTransition(alert=self._alerts[rule], previous=previous, current=current)
