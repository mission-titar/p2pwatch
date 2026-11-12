"""The restart policy: a bugs condition entering failing restarts its component's owner, at most
three times in vain; every bugs condition of the owner's components healthy again resets the count
(spec v5 lot 4, D5, appendix A "Restarts")."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import BUGS, Health

# OTP's bounded restart intensity: past it, restarting is taken to repair nothing.
USELESS_RESTARTS_AT_MOST = 3


# Restarting from its request to its rebuild; restarted, a bugs condition failing again makes the
# restart useless.
type _Phase = Literal["steady", "restarting", "restarted", "given up"]


@dataclass(kw_only=True)
class _OwnerState:
    phase: _Phase = "steady"
    useless: int = 0


class RestartPolicy:
    """The recorder's subscriber deciding each restart, which the supervisor takes and runs."""

    def __init__(self, *, owners: Mapping[Component, StateOwner], logger: Logger) -> None:
        for component in owners:
            if component.health_of(BUGS) is None:
                raise ValueError(f"{component.name}: a bugs condition expected")
        self._owners = dict(owners)
        self._states = {owner: _OwnerState() for owner in owners.values()}
        self._logger = logger
        self._requests: asyncio.Queue[StateOwner] = asyncio.Queue()

    def components_of(self, owner: StateOwner) -> tuple[Component, ...]:
        """The components the composition names ``owner`` the owner of."""
        return tuple(component for component, its in self._owners.items() if its is owner)

    async def __call__(self, transition: HealthTransition) -> None:
        owner = self._owners.get(transition.component)
        if owner is None or transition.condition != BUGS:
            return
        state = self._states[owner]
        if transition.current is Health.FAILING:
            self._on_failing(transition.component, owner=owner, state=state)
        elif all(c.health_of(BUGS) is Health.HEALTHY for c in self.components_of(owner)):
            state.phase, state.useless = "steady", 0

    async def requested(self) -> StateOwner:
        """Returns the next owner to restart, once one is due."""
        return await self._requests.get()

    def rebuilt(self, owner: StateOwner) -> None:
        """``owner``'s restart built it anew."""
        self._states[owner].phase = "restarted"

    def rebuild_raised(self, owner: StateOwner) -> bool:
        """Counts ``owner``'s restart useless; whether to try it again."""
        state = self._states[owner]
        state.useless += 1
        return not self._gave_up(owner, state=state)

    def _on_failing(self, component: Component, *, owner: StateOwner, state: _OwnerState) -> None:
        if state.phase == "restarted":
            state.useless += 1
            if self._gave_up(owner, state=state):
                return
        elif state.phase != "steady":
            return  # a restart is coming, or none will
        state.phase = "restarting"
        self._logger.warning("%s, bugs failing: restarting %s", component.name, owner)
        self._requests.put_nowait(owner)

    def _gave_up(self, owner: StateOwner, *, state: _OwnerState) -> bool:
        if state.useless < USELESS_RESTARTS_AT_MOST:
            return False
        state.phase = "given up"
        self._logger.error(
            "%s: %d useless restarts, its components failing; not restarted again",
            owner,
            state.useless,
        )
        return True
