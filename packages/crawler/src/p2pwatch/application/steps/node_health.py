"""The node's health, which every check of every part goes through."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthTransition
from p2pwatch.domain.health.health_rule import HealthRule, HealthState


# What NodeHealth passes each change of health to, such as HealthAlerter.send.
class HealthSubscriber(Protocol):
    async def __call__(self, transition: HealthTransition) -> None: ...


class NodeHealth:
    """The node's health: every part's checks come here, and each change is logged and passed on
    to its subscribers, such as the alerts."""

    def __init__(self, *, logger: Logger, subscribers: Sequence[HealthSubscriber]) -> None:
        self._logger = logger
        self._subscribers = tuple(subscribers)  # called in this order

    async def record(self, *, on: ExternalDependency, rule: HealthRule, detected: bool) -> None:
        """Records one check of ``rule`` on ``on``, such as a status reading aMule did not
        answer."""
        transition = on.record(rule=rule, detected=detected)
        if transition is None:
            return
        failing = transition.current is HealthState.FAILING
        log = self._logger.warning if failing else self._logger.info
        previous, current = transition.previous.value, transition.current.value
        log("%s, %s: %s to %s", on.name, rule.name, previous, current)
        for subscriber in self._subscribers:
            await subscriber(transition)
