"""The promise of the ``StateOwner`` port."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.state_owner import StateOwner


class StateOwnerContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def owner(self) -> StateOwner:
        """An owner holding its first state, no restart run yet."""

    @abstractmethod
    def state_of(self, owner: StateOwner) -> object:
        """The in-memory state ``owner`` holds now."""

    @abstractmethod
    async def state_relied_on(self, owner: StateOwner) -> object:
        """The state what relies on ``owner`` reaches now: the latest work it added to the
        supervisor, or what reaches the state through ``owner`` itself."""

    async def test_a_restart_builds_its_state_anew(self, owner: StateOwner) -> None:
        first = self.state_of(owner)
        await owner.restart()
        assert self.state_of(owner) is not first

    async def test_each_restart_leaves_what_relies_on_it_on_the_state_it_built(
        self, owner: StateOwner
    ) -> None:
        for _ in range(2):
            await owner.restart()
            assert await self.state_relied_on(owner) is self.state_of(owner)
