import pytest

from tests.contracts.application.ports.driven.wall_clock_contract import WallClockContract
from tests.fakes.adapters.driven.fake_ticking_wall_clock import FakeTickingWallClock
from tests.fakes.adapters.driven.fake_time import FakeTime


class TestFakeTickingWallClock(WallClockContract):
    @pytest.fixture
    def wall_clock(self) -> FakeTickingWallClock:
        return FakeTickingWallClock(FakeTime())
