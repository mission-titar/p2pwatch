"""The parts of the node whose health is tracked."""

from dataclasses import dataclass

from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import Channel, ClientName


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """A change of one part's state under one rule, such as the aMule client going from healthy to
    failing."""

    component: "Component"
    rule: HealthRule
    previous: HealthState
    current: HealthState


class Component:
    """A part of the node whose health is tracked, such as the aMule client or its Kad channel."""

    def __init__(
        self,
        *,
        name: str,
        client_name: ClientName,
        channel: Channel | None = None,
        rules: tuple[HealthRule, ...],
    ) -> None:
        self.name = name  # "client amuled", as the log names it
        self.client_name = client_name  # "amuled", as the alerts name it
        self.channel = channel  # "kad" for a part of one channel, as the alerts name it
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
        return HealthTransition(component=self, rule=rule, previous=previous, current=current)
