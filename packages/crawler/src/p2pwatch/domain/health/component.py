"""A component: a part of the node whose health its conditions judge."""

from dataclasses import dataclass

from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome
from p2pwatch.domain.identifiers import ClientName


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """One condition of one component changing its health."""

    component: "Component"
    condition: HealthCondition
    previous: Health
    current: Health


class Component:
    """Keeps each condition's latest outcomes and the health they gave."""

    def __init__(
        self, *, name: str, client_name: ClientName, conditions: tuple[HealthCondition, ...]
    ) -> None:
        self.name = name  # as the log names it
        self.client_name = client_name  # the client it is part of, as the alerts name it
        self._latest_outcomes: dict[HealthCondition, tuple[Outcome, ...]]
        self._latest_outcomes = dict.fromkeys(conditions, ())
        self._health = dict.fromkeys(conditions, Health.UNKNOWN)

    def record(self, outcome: Outcome, *, condition: HealthCondition) -> HealthTransition | None:
        """Judges ``condition`` again with ``outcome``; returns its change of health, if any."""
        latest = (*self._latest_outcomes[condition], outcome)[-condition.outcomes_kept :]
        previous = self._health[condition]
        current = condition.health_after(latest, previous=previous)
        self._latest_outcomes[condition], self._health[condition] = latest, current
        if current is previous:
            return None
        return HealthTransition(
            component=self, condition=condition, previous=previous, current=current
        )
