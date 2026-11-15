"""The parts of the node whose health is tracked."""

from dataclasses import dataclass

from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import ClientName


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """A change in one part's health, such as the aMule client going from healthy to failing."""

    component: "Component"
    rule: HealthRule
    previous: HealthState
    current: HealthState


class Component:
    """A part of the node whose health is tracked, such as the aMule client."""

    def __init__(
        self, *, name: str, client_name: ClientName, rules: tuple[HealthRule, ...]
    ) -> None:
        self.name = name  # "client amuled", as the log names it
        self.client_name = client_name  # "amuled", as the alerts name it
        self._latest_failed: dict[HealthRule, tuple[bool, ...]] = dict.fromkeys(rules, ())
        self._states = dict.fromkeys(rules, HealthState.UNKNOWN)

    def record_failure(self, error: Exception, *, rule: HealthRule) -> HealthTransition | None:
        """Counts a failed attempt for ``rule``, as working if it failed with another error;
        returns the change of health it caused, if any."""
        return self._record(isinstance(error, rule.counts), rule=rule)

    def record_success(self, *, rule: HealthRule) -> HealthTransition | None:
        """Counts an attempt that worked for ``rule``; returns the change it caused, if any."""
        return self._record(False, rule=rule)

    def _record(self, failed: bool, *, rule: HealthRule) -> HealthTransition | None:
        latest_failed = (*self._latest_failed[rule], failed)[-rule.attempts_kept :]
        previous = self._states[rule]
        current = rule.state_after(latest_failed, previous=previous)
        self._latest_failed[rule], self._states[rule] = latest_failed, current
        if current is previous:
            return None
        return HealthTransition(component=self, rule=rule, previous=previous, current=current)
