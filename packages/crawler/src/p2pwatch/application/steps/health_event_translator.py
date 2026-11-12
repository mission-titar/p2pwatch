"""The health event translator: the readings' transitions become today's connectivity events, an
alert on entering failing, its end only on a return to healthy after it (spec v5 lot 4, D21)."""

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.health.component import HealthTransition
from p2pwatch.domain.health.health_condition import Health
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import ClientReachableAgain, ClientUnreachableLasting
from p2pwatch.domain.status_reading import CLIENT_UNREACHABLE, lasting_at_entry


class HealthEventTranslator:
    """A subscriber of the health recorder, dispatching the events the transitions stand for."""

    def __init__(
        self, *, observability_dispatcher: ObservabilityDispatcher, node_id: NodeId
    ) -> None:
        self._observability_dispatcher = observability_dispatcher
        self._node_id = node_id

    async def translate(self, transition: HealthTransition) -> None:
        if transition.condition != CLIENT_UNREACHABLE:
            return
        client_name = transition.component.labels.client_name
        if transition.current is Health.FAILING:
            await self._observability_dispatcher.dispatch(
                ClientUnreachableLasting(
                    client_name=client_name,
                    unreachable_for_seconds=lasting_at_entry(CLIENT_UNREACHABLE).total_seconds(),
                    node_id=self._node_id,
                )
            )
        elif transition.previous is Health.FAILING:  # unknown to healthy ends no alert
            await self._observability_dispatcher.dispatch(
                ClientReachableAgain(client_name=client_name, node_id=self._node_id)
            )
