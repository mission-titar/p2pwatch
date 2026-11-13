"""The parts of the node whose health is tracked."""

from dataclasses import dataclass

from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome
from p2pwatch.domain.identifiers import ClientName


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """A change in one part's health, such as the aMule client going from healthy to failing."""

    component: "Component"
    condition: HealthCondition
    previous: Health
    current: Health


class Component:
    """A part of the node whose health is tracked, such as the aMule client."""

    def __init__(
        self, *, name: str, client_name: ClientName, conditions: tuple[HealthCondition, ...]
    ) -> None:
        self.name = name  # "client amuled", as the log names it
        self.client_name = client_name  # "amuled", as the alerts name it
        self._latest_outcomes: dict[HealthCondition, tuple[Outcome, ...]]
        self._latest_outcomes = dict.fromkeys(conditions, ())
        self._health = dict.fromkeys(conditions, Health.UNKNOWN)

    def record(self, outcome: Outcome, *, condition: HealthCondition) -> HealthTransition | None:
        """Counts ``outcome`` for ``condition``; returns the change of health it caused, if any."""
        latest = (*self._latest_outcomes[condition], outcome)[-condition.outcomes_kept :]
        previous = self._health[condition]
        current = condition.health_after(latest, previous=previous)
        self._latest_outcomes[condition], self._health[condition] = latest, current
        if current is previous:
            return None
        return HealthTransition(
            component=self, condition=condition, previous=previous, current=current
        )
