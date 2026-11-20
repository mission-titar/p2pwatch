"""The alert of each change of health whose rule has one."""

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.external_dependency import HealthTransition


class HealthAlerter:
    """Sends the alert of each change of health whose rule has one, such as "amuled unreachable
    for 2 min" when the client starts failing."""

    def __init__(self, *, observability_dispatcher: ObservabilityDispatcher) -> None:
        self._observability_dispatcher = observability_dispatcher

    async def send(self, transition: HealthTransition) -> None:
        if (alert := transition.alert_event()) is not None:
            await self._observability_dispatcher.dispatch(alert)
