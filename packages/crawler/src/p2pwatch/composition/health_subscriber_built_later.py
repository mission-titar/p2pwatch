"""A subscriber of the node's health built after it, such as the restart policy, which maps the
parts the works are recorded on, the works recording on the node's health."""

from p2pwatch.application.steps.node_health import HealthSubscriber
from p2pwatch.domain.health.component import HealthTransition


class HealthSubscriberNotSetError(RuntimeError):
    """A subscriber reached before the composition set it: a bug of the order the node is built
    in."""


class HealthSubscriberBuiltLater:
    """Passes each change of health on to ``subscriber``, such as the restart policy, once the
    composition set it."""

    def __init__(self, subscriber: str) -> None:
        self._subscriber_name = subscriber
        self._subscriber: HealthSubscriber | None = None

    def set(self, subscriber: HealthSubscriber) -> None:
        self._subscriber = subscriber

    async def __call__(self, transition: HealthTransition) -> None:
        """Hands ``transition`` to the subscriber, raising if it is not set yet."""
        if self._subscriber is None:
            raise HealthSubscriberNotSetError(f"{self._subscriber_name}, reached before it is set")
        await self._subscriber(transition)
