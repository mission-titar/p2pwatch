import asyncio
from datetime import datetime, timedelta

from p2pwatch.application.ports.driven.wall_clock import WallClock
from tests.support.virtual_time import EPOCH


class FakeLoopWallClock(WallClock):
    """The running loop's time as the ``WallClock`` port."""

    def now(self) -> datetime:
        return EPOCH + timedelta(seconds=asyncio.get_running_loop().time())
