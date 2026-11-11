"""The health recorder: every outcome is recorded through it, on one component by one source; each
transition it causes is written in one log line, then handed to every subscriber in order."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health
from p2pwatch.domain.health.outcome import Outcome, OutcomeSource


class HealthSubscriber(Protocol):
    async def __call__(self, transition: HealthTransition) -> None: ...


class HealthRecorder:
    """The one fan-out of the health transitions."""

    def __init__(self, *, logger: Logger, subscribers: Sequence[HealthSubscriber]) -> None:
        self._logger = logger
        self._subscribers = tuple(subscribers)

    async def record(self, outcome: Outcome, *, on: Component, by: OutcomeSource) -> None:
        for transition in on.record(outcome, by=by):
            unwell = transition.current in (Health.DEGRADED, Health.FAILING)
            log = self._logger.warning if unwell else self._logger.info
            log(
                "%s, %s: %s to %s",
                on.name,
                transition.condition.name,
                transition.previous.value,
                transition.current.value,
            )
            for subscriber in self._subscribers:
                await subscriber(transition)
