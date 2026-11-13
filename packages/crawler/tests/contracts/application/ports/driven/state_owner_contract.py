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
    def states_relied_on(self, owner: StateOwner) -> list[object]:
        """The state the works of each addition to the supervisor rely on, in order."""

    async def test_a_restart_builds_its_state_anew(self, owner: StateOwner) -> None:
        first = self.state_of(owner)
        await owner.restart()
        assert self.state_of(owner) is not first

    async def test_each_restart_adds_works_relying_on_the_state_it_built(
        self, owner: StateOwner
    ) -> None:
        built = []
        for _ in range(2):
            await owner.restart()
            built.append(self.state_of(owner))
        relied_on = self.states_relied_on(owner)
        assert len(relied_on) == len(built)
        assert all(state is new for state, new in zip(relied_on, built, strict=True))
