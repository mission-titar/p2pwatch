"""The health event translator: the alerts "unreachable for 2 min", then "reachable again"."""

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.health.health_condition import Health
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import ClientReachableAgain, ClientUnreachableLasting
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE, UNREACHABLE_ALERT_AFTER


class HealthEventTranslator:
    """A subscriber of the health recorder, dispatching the event a change of health stands for."""

    def __init__(
        self, *, observability_dispatcher: ObservabilityDispatcher, node_id: NodeId
    ) -> None:
        self._observability_dispatcher = observability_dispatcher
        self._node_id = node_id

    async def translate(self, transition: HealthTransition) -> None:
        if transition.condition != CLIENT_UNREACHABLE:
            return
        client_name = transition.component.client_name
        if transition.current is Health.FAILING:
            await self._observability_dispatcher.dispatch(
                ClientUnreachableLasting(
                    client_name=client_name,
                    unreachable_for_seconds=UNREACHABLE_ALERT_AFTER.total_seconds(),
                    node_id=self._node_id,
                )
            )
        elif transition.previous is Health.FAILING:  # from unknown to healthy, no alert to end
            await self._observability_dispatcher.dispatch(
                ClientReachableAgain(client_name=client_name, node_id=self._node_id)
            )
