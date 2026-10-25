import pytest

from tests.contracts.application.ports.driven.waker_contract import WakerContract
from tests.fakes.adapters.driven.fake_waker import FakeWaker


class TestFakeWaker(WakerContract):
    @pytest.fixture
    def waker(self) -> FakeWaker:
        return FakeWaker()
