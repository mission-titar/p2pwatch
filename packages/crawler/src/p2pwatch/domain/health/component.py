"""A component: a part of the node judged by its conditions, each over its own window."""

from dataclasses import dataclass

from p2pwatch.domain.health.health_condition import ConditionWindow, Health, HealthCondition
from p2pwatch.domain.health.outcome import Outcome, OutcomeSource
from p2pwatch.domain.identifiers import ClientName


@dataclass(kw_only=True, frozen=True)
class ComponentLabels:
    """What the events and the metrics name a component by."""

    client_name: ClientName


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """One condition of one component changing its health."""

    component: "Component"
    condition: HealthCondition
    previous: Health
    current: Health


class Component:
    """Holds a window per condition: an outcome feeds the conditions of its source alone."""

    def __init__(
        self, *, name: str, labels: ComponentLabels, conditions: tuple[HealthCondition, ...]
    ) -> None:
        self.name = name
        self.labels = labels
        self._windows = [ConditionWindow(condition=condition) for condition in conditions]

    def record(self, outcome: Outcome, *, by: OutcomeSource) -> tuple[HealthTransition, ...]:
        """Feeds ``outcome`` to each condition reading ``by``; returns the changes it caused."""
        transitions: list[HealthTransition] = []
        for index, window in enumerate(self._windows):
            if window.condition.source != by:
                continue
            self._windows[index] = after = window.after(outcome)
            if after.health is not window.health:
                transitions.append(
                    HealthTransition(
                        component=self,
                        condition=window.condition,
                        previous=window.health,
                        current=after.health,
                    )
                )
        return tuple(transitions)
