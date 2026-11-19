"""The promise of the ``RestartableBuilder`` port and of the objects it builds."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder


class RestartableBuilderContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def restartable_builder(self) -> RestartableBuilder[object]:
        """A builder that has built nothing yet."""

    @abstractmethod
    def state_of(self, restartable: Restartable[object]) -> object:
        """The state ``restartable`` was built with, such as the aMule client it logged in."""

    @abstractmethod
    def state_reached(self, restartable: Restartable[object]) -> object:
        """The state its works run over, such as the client their requests go to."""

    async def test_each_build_holds_a_state_of_its_own(
        self, restartable_builder: RestartableBuilder[object]
    ) -> None:
        first = self.state_of(await restartable_builder.build())

        second = self.state_of(await restartable_builder.build())

        assert second is not first

    async def test_the_works_of_each_object_run_over_the_state_it_was_built_with(
        self, restartable_builder: RestartableBuilder[object]
    ) -> None:
        for _ in range(2):
            restartable = await restartable_builder.build()

            assert self.state_reached(restartable) is self.state_of(restartable)

    async def test_a_second_close_raises_nothing(
        self, restartable_builder: RestartableBuilder[object]
    ) -> None:
        restartable = await restartable_builder.build()
        await restartable.close()

        await restartable.close()
