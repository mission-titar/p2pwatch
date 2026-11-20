"""The node's health, which every check of every part goes through."""

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.health.health_rule import HealthRule, HealthState


class NodeHealth:
    """The node's health: every part's checks come here, and each change is logged and its rule's
    alert dispatched, such as "amuled unreachable for 2 min"."""

    def __init__(
        self, *, logger: Logger, observability_dispatcher: ObservabilityDispatcher
    ) -> None:
        self._logger = logger
        self._observability_dispatcher = observability_dispatcher

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
        if (alert := transition.alert_event()) is not None:
            await self._observability_dispatcher.dispatch(alert)
