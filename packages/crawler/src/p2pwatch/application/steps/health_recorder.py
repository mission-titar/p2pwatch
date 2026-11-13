"""The health recorder: every outcome goes through it, so each change of health is logged once."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome


class HealthSubscriber(Protocol):
    async def __call__(self, transition: HealthTransition) -> None: ...


class HealthRecorder:
    """Logs each change of health an outcome causes, then passes it to each subscriber in order."""

    def __init__(self, *, logger: Logger, subscribers: Sequence[HealthSubscriber]) -> None:
        self._logger = logger
        self._subscribers = tuple(subscribers)  # the alerts today, the restarts to come

    async def record(self, outcome: Outcome, *, on: Component, condition: HealthCondition) -> None:
        transition = on.record(outcome, condition=condition)
        if transition is None:
            return
        log = self._logger.warning if transition.current is Health.FAILING else self._logger.info
        previous, current = transition.previous.value, transition.current.value
        log("%s, %s: %s to %s", on.name, condition.name, previous, current)
        for subscriber in self._subscribers:
            await subscriber(transition)
