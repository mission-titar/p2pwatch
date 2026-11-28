"""What the node depends on and does not control, its health tracked, each rule with the alert it
sends and its end."""

from collections.abc import Mapping
from dataclasses import dataclass

from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.observability.events import Event


@dataclass(kw_only=True, frozen=True)
class HealthAlert:
    """An alert and its end, opened and ended through the node's health: a rule of a part's, such
    as Kad's "off its network for 5 min", then "back on its network", or an object unrepaired."""

    about: str  # its key among the open ones: "client amuled, unreachable", "client amuled"
    when_failing: Event
    when_healthy_again: Event


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """A change of one part's state under one rule, such as the aMule client going from healthy to
    failing, with that rule's alert."""

    alert: HealthAlert
    previous: HealthState
    current: HealthState


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
