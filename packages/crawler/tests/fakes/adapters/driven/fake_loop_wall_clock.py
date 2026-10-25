import asyncio
from datetime import datetime, timedelta

from p2pwatch.application.ports.driven.wall_clock import WallClock
from tests.support.virtual_time import EPOCH


class FakeLoopWallClock(WallClock):
    """The time of the loop it is given as the ``WallClock`` port."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def now(self) -> datetime:
        return EPOCH + timedelta(seconds=self._loop.time())
