"""The node's health, which every part's outcomes go through."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import HealthCondition, HealthState


# What NodeHealth passes each change of health to, such as HealthAlerts.send.
class HealthSubscriber(Protocol):
    async def __call__(self, transition: HealthTransition) -> None: ...


class NodeHealth:
    """The node's health: every part's outcomes come here, and each change is logged and passed on
    to the alerts (and, later, to the restarts)."""

    def __init__(self, *, logger: Logger, subscribers: Sequence[HealthSubscriber]) -> None:
        self._logger = logger
        self._subscribers = tuple(subscribers)  # called in this order

    async def record_failure(
        self, failure: DeclaredFailure, *, on: Component, condition: HealthCondition
    ) -> None:
        await self._pass_on(on.record_failure(failure, condition=condition))

    async def record_success(self, *, on: Component, condition: HealthCondition) -> None:
        await self._pass_on(on.record_success(condition=condition))

    async def _pass_on(self, transition: HealthTransition | None) -> None:
        if transition is None:
            return
        failing = transition.current is HealthState.FAILING
        log = self._logger.warning if failing else self._logger.info
        part, condition = transition.component.name, transition.condition.name
        previous, current = transition.previous.value, transition.current.value
        log("%s, %s: %s to %s", part, condition, previous, current)
        for subscriber in self._subscribers:
            await subscriber(transition)
