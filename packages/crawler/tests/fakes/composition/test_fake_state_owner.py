import pytest

from p2pwatch.application.ports.driven.state_owner import StateOwner
from tests.contracts.application.ports.driven.state_owner_contract import StateOwnerContract
from tests.fakes.composition.fake_state_owner import FakeStateOwner


class TestFakeStateOwner(StateOwnerContract):
    @pytest.fixture
    def owner(self) -> FakeStateOwner:
        relied_on: list[object] = []
        owner = FakeStateOwner(add_works=relied_on.append)
        self._relied_on = relied_on
        return owner

    def state_of(self, owner: StateOwner) -> object:
        assert isinstance(owner, FakeStateOwner)
        return owner.state

    def states_relied_on(self, owner: StateOwner) -> list[object]:
        return self._relied_on


@pytest.mark.asyncio
async def test_a_raising_restart_builds_nothing_and_keeps_its_attempt() -> None:
    relied_on: list[object] = []
    owner = FakeStateOwner("client", add_works=relied_on.append, raising=[LookupError("down")])
    first = owner.state

    with pytest.raises(LookupError, match="down"):
        await owner.restart()
    await owner.restart()

    assert str(owner) == "client"
    assert len(owner.attempts) == 2
    assert relied_on == [owner.state] and owner.state is not first
