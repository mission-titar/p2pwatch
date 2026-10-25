import asyncio

import pytest_asyncio

from tests.contracts.application.ports.driven.wall_clock_contract import WallClockContract
from tests.fakes.adapters.driven.fake_loop_wall_clock import FakeLoopWallClock


class TestFakeLoopWallClock(WallClockContract):
    @pytest_asyncio.fixture
    async def wall_clock(self) -> FakeLoopWallClock:
        return FakeLoopWallClock(asyncio.get_running_loop())
