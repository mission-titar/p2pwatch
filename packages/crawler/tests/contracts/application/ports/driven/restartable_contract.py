"""The promise of the ``Restartable`` port."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

import pytest

from p2pwatch.application.ports.driven.restartable import Restartable


class RestartableContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def restartable(self) -> Restartable[object]:
        """An object holding its first state, never rebuilt yet."""

    @abstractmethod
    def state_of(self, restartable: Restartable[object]) -> object:
        """The state ``restartable`` holds now, such as the aMule client it built latest."""

    @abstractmethod
    def state_under(self, works: Sequence[object]) -> object:
        """The state ``works`` run over, such as the aMule client they send their requests to."""

    async def test_a_rebuild_builds_its_state_anew(self, restartable: Restartable[object]) -> None:
        first = self.state_of(restartable)

        await restartable.rebuild()

        assert self.state_of(restartable) is not first

    async def test_the_works_each_rebuild_hands_back_run_over_the_state_it_built(
        self, restartable: Restartable[object]
    ) -> None:
        for _ in range(2):
            works = await restartable.rebuild()

            assert self.state_under(works) is self.state_of(restartable)
