"""The node's health, which every check of every part goes through, and every alert opens and
ends through."""

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthAlert
from p2pwatch.domain.health.health_rule import HealthRule, HealthState


class NodeHealth:
    """The node's health: every part's checks come here, each change logged and its rule's alert
    opened or ended, such as "amuled unreachable for 2 min"; it keeps the alerts open."""

    def __init__(
        self, *, logger: Logger, observability_dispatcher: ObservabilityDispatcher
    ) -> None:
        self._logger = logger
        self._observability_dispatcher = observability_dispatcher
        self._open: dict[str, HealthAlert] = {}  # by what each is about: "client amuled"

    async def record(self, *, on: ExternalDependency, rule: HealthRule, detected: bool) -> None:
        """Records one check of ``rule`` on ``on``, such as a status reading aMule did not
        answer."""
        transition = on.record(rule=rule, detected=detected)
        if transition is None:
            return
        failing = transition.current is HealthState.FAILING
        log = self._logger.warning if failing else self._logger.info
        previous, current = transition.previous.value, transition.current.value
        log("%s: %s to %s", transition.alert.about, previous, current)
        if failing:
            await self.open_alert(transition.alert)
        else:
            await self.end_alert(about=transition.alert.about)

    async def open_alert(self, alert: HealthAlert) -> None:
        """Dispatches ``alert``'s opening and keeps it open, such as an object left unrepaired;
        one already open by what it is about does nothing."""
        if alert.about in self._open:
            return
        self._open[alert.about] = alert
        await self._observability_dispatcher.dispatch(alert.when_failing)

    async def end_alert(self, *, about: str) -> None:
        """Dispatches the end of the alert open ``about`` and drops it, such as "client amuled"
        repaired; one not open does nothing."""
        if (alert := self._open.pop(about, None)) is None:
            return
        await self._observability_dispatcher.dispatch(alert.when_healthy_again)
