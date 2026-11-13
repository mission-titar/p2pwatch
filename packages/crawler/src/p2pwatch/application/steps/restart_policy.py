"""The restart policy: a bugs condition entering failing requests its owner's restart, at most three
times in vain; every bugs condition of the owner's components healthy again resets the count."""

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import UNITS_OF_WORK

# OTP's bounded restart intensity: past it, restarting is taken to repair nothing.
USELESS_RESTARTS_AT_MOST = 3


# Restarting from its request to its rebuild; restarted, a bugs condition failing again makes the
# restart useless.
type _Phase = Literal["steady", "restarting", "restarted", "given up"]


@dataclass(kw_only=True)
class _OwnerState:
    owner: StateOwner
    logger: Logger
    phase: _Phase = "steady"
    useless: int = 0

    def count_useless(self) -> bool:
        """Counts a useless restart; whether to restart again, the owner given up past the bound."""
        self.useless += 1
        if self.useless < USELESS_RESTARTS_AT_MOST:
            return True
        self.phase = "given up"
        self.logger.error(
            "%s: %d useless restarts, its components failing; not restarted again",
            self.owner,
            self.useless,
        )
        return False


class RestartRequest:
    """One restart the policy requests: the supervisor stops the works feeding its components,
    restarts its owner, then tells the request how the rebuild ended."""

    def __init__(self, *, components: tuple[Component, ...], state: _OwnerState) -> None:
        self.owner = state.owner
        self.components = components
        self._state = state

    def rebuilt(self) -> None:
        """Its owner built anew: its components' bugs windows emptied, their other windows kept."""
        for component in self.components:
            component.empty_windows(of=UNITS_OF_WORK)
        self._state.phase = "restarted"

    def rebuild_raised(self) -> bool:
        """Counts the restart useless; whether to try the rebuild again."""
        return self._state.count_useless()


class RestartPolicy:
    """The recorder's subscriber deciding each restart, which the supervisor takes and runs."""

    def __init__(self, *, owners: Mapping[Component, StateOwner], logger: Logger) -> None:
        for component in owners:
            if component.health_of(BUGS) is None:
                raise ValueError(f"{component.name}: a bugs condition expected")
        self._owners = dict(owners)
        self._states = {owner: _OwnerState(owner=owner, logger=logger) for owner in owners.values()}
        self._logger = logger
        self._requests: asyncio.Queue[RestartRequest] = asyncio.Queue()

    async def __call__(self, transition: HealthTransition) -> None:
        if transition.condition != BUGS:
            return
        # Every component a work feeds or the dispatcher records on is owned, by construction.
        owner = self._owners[transition.component]
        state = self._states[owner]
        if transition.current is Health.FAILING:
            self._on_failing(transition.component, state=state)
        elif all(c.health_of(BUGS) is Health.HEALTHY for c in self._components_of(owner)):
            state.phase, state.useless = "steady", 0

    async def requested(self) -> RestartRequest:
        """Returns the next restart, once one is due."""
        return await self._requests.get()

    def _components_of(self, owner: StateOwner) -> tuple[Component, ...]:
        return tuple(component for component, its in self._owners.items() if its is owner)

    def _on_failing(self, component: Component, *, state: _OwnerState) -> None:
        if state.phase == "restarted":
            if not state.count_useless():
                return
        elif state.phase != "steady":
            return  # a restart is coming, or none will
        state.phase = "restarting"
        self._logger.warning("%s, bugs failing: restarting %s", component.name, state.owner)
        self._requests.put_nowait(
            RestartRequest(components=self._components_of(state.owner), state=state)
        )
