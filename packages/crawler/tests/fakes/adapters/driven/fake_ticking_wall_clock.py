from datetime import datetime, timedelta

from tests.fakes.adapters.driven.fake_wall_clock import FakeWallClock


class FakeTickingWallClock(FakeWallClock):
    """Each ``now()`` a minute after the previous one: a write shows which read it took."""

    def now(self) -> datetime:
        moment = super().now()
        self._fake_time.advance(timedelta(minutes=1))
        return moment
