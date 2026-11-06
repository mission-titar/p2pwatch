import asyncio

import pytest

from tests.contracts.application.ports.driven.wall_clock_contract import WallClockContract
from tests.fakes.adapters.driven.fake_loop_wall_clock import FakeLoopWallClock


class TestFakeLoopWallClock(WallClockContract):
    @pytest.fixture
    def wall_clock(self, running_loop: asyncio.AbstractEventLoop) -> FakeLoopWallClock:
        return FakeLoopWallClock(running_loop)
