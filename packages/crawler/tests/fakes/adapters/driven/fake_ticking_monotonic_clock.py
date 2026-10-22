from datetime import timedelta

from p2pwatch.domain.monotonic_instant import MonotonicInstant
from tests.fakes.adapters.driven.fake_monotonic_clock import FakeMonotonicClock


class FakeTickingMonotonicClock(FakeMonotonicClock):
    """Each ``now()`` a second after the previous one: a query's every check sees time pass."""

    def now(self) -> MonotonicInstant:
        moment = super().now()
        self._fake_time.advance(timedelta(seconds=1))
        return moment
