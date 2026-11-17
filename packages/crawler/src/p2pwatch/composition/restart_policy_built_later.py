"""The restart policy as the node's health reaches it: built after the node's health, since the
policy maps the parts the works are recorded on, and the works record on the node's health."""

from p2pwatch.application.steps.restart_policy import RestartPolicy
from p2pwatch.domain.health.component import HealthTransition


class RestartPolicyNotSetError(RuntimeError):
    """The restart policy reached before the composition set it: a bug of the order the node is
    built in."""


class RestartPolicyBuiltLater:
    """Passes each change of health on to the restart policy once the composition set it."""

    def __init__(self) -> None:
        self._restart_policy: RestartPolicy | None = None

    def set(self, restart_policy: RestartPolicy) -> None:
        self._restart_policy = restart_policy

    async def __call__(self, transition: HealthTransition) -> None:
        """Hands ``transition`` to the policy, raising if it is not set yet."""
        if self._restart_policy is None:
            raise RestartPolicyNotSetError("the restart policy, reached before it is set")
        await self._restart_policy(transition)
