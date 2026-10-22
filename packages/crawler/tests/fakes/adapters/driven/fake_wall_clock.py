from datetime import datetime
from typing import TYPE_CHECKING

from p2pwatch.application.ports.driven.wall_clock import WallClock

if TYPE_CHECKING:  # a cycle: FakeTime builds its clocks
    from tests.fakes.adapters.driven.fake_time import FakeTime


class FakeWallClock(WallClock):
    def __init__(self, fake_time: "FakeTime") -> None:
        self._fake_time = fake_time

    def now(self) -> datetime:
        return self._fake_time._wall_now
