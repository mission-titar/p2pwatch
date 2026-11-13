"""The health recorder: the one place every outcome goes through."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome


# What the recorder passes each change of health to, such as HealthAlerts.send.
class HealthSubscriber(Protocol):
    async def __call__(self, transition: HealthTransition) -> None: ...


class HealthRecorder:
    """Updates a part's health with each new outcome, logs every change, and passes the change on
    to the alerts (and, later, to the restarts)."""

    def __init__(self, *, logger: Logger, subscribers: Sequence[HealthSubscriber]) -> None:
        self._logger = logger
        self._subscribers = tuple(subscribers)  # called in this order

    async def record(self, outcome: Outcome, *, on: Component, condition: HealthCondition) -> None:
        transition = on.record(outcome, condition=condition)
        if transition is None:
            return
        log = self._logger.warning if transition.current is Health.FAILING else self._logger.info
        previous, current = transition.previous.value, transition.current.value
        log("%s, %s: %s to %s", on.name, condition.name, previous, current)
        for subscriber in self._subscribers:
            await subscriber(transition)
