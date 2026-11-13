"""A component: a part of the node judged by its conditions, each over its own window."""

from dataclasses import dataclass

from p2pwatch.domain.health.health_condition import ConditionWindow, Health, HealthCondition
from p2pwatch.domain.health.outcome import Outcome, OutcomeSource
from p2pwatch.domain.identifiers import Channel, ClientName


@dataclass(kw_only=True, frozen=True)
class ComponentLabels:
    """What the events and the metrics name a component by."""

    client_name: ClientName | None = None  # None: a part of no client, the webui
    channel: Channel | None = None  # None: a component of the whole client


@dataclass(kw_only=True, frozen=True)
class HealthTransition:
    """One condition of one component changing its health, and the outcome that changed it."""

    component: "Component"
    condition: HealthCondition
    previous: Health
    current: Health
    outcome: Outcome  # its reason carries the reading today's events quote


class Component:
    """Holds a window per condition: an outcome feeds the conditions of its source alone."""

    def __init__(
        self, *, name: str, labels: ComponentLabels, conditions: tuple[HealthCondition, ...]
    ) -> None:
        self.name = name
        self.labels = labels
        self._windows = [ConditionWindow(condition=condition) for condition in conditions]

    def reads(self, source: OutcomeSource) -> bool:
        """Whether a condition of it reads ``source``."""
        return any(window.condition.source == source for window in self._windows)

    def health_of(self, condition: HealthCondition) -> Health | None:
        """The health ``condition`` gives it, ``None`` when it does not carry it."""
        return next((w.health for w in self._windows if w.condition == condition), None)

    def empty_windows(self, *, of: OutcomeSource) -> None:
        """Forgets the outcomes of ``of``: its conditions unknown again, giving no transition."""
        self._windows = [
            ConditionWindow(condition=w.condition) if w.condition.source == of else w
            for w in self._windows
        ]

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
                        outcome=outcome,
                    )
                )
        return tuple(transitions)
