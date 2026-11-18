"""The promise of the ``RestartableBuilder`` port and of the objects it builds."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder


class RestartableBuilderContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def builder(self) -> RestartableBuilder[Restartable[object]]:
        """A builder that has built nothing yet."""

    @abstractmethod
    def state_of(self, restartable: Restartable[object]) -> object:
        """The state ``restartable`` was built with, read right after its build, such as the aMule
        client it logged in."""

    @abstractmethod
    def state_reached(self, restartable: Restartable[object]) -> object:
        """The state its works run over, such as the client their requests go to; for an object
        no work runs over, the state its users reach."""

    async def test_each_build_holds_a_state_of_its_own(
        self, builder: RestartableBuilder[Restartable[object]]
    ) -> None:
        first = self.state_of(await builder.build())

        second = self.state_of(await builder.build())

        assert second is not first

    async def test_what_each_object_offers_reaches_the_state_it_was_built_with(
        self, builder: RestartableBuilder[Restartable[object]]
    ) -> None:
        for _ in range(2):
            restartable = await builder.build()

            assert self.state_reached(restartable) is self.state_of(restartable)

    async def test_closing_it_twice_raises_nothing(
        self, builder: RestartableBuilder[Restartable[object]]
    ) -> None:
        restartable = await builder.build()
        await restartable.close()

        await restartable.close()
