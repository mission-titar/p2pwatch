import pytest

from tests.contracts.application.ports.driven.wall_clock_contract import WallClockContract
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock


class TestFakeWallClock(WallClockContract):
    @pytest.fixture
    def wall_clock(self) -> FakeWallClock:
        return FakeTime().wall
