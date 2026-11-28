"""``FunctionProgress``: each watched function's latest progress, such as the latest search that
moved the crawl on amuled's kad."""

from datetime import timedelta

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.watched_function import WatchedFunction


class FunctionProgress:
    """Each watched function's latest progress on the monotonic clock, built once per client so
    that a client built anew counts on from where the old one left."""

    def __init__(self, *, monotonic_clock: MonotonicClock) -> None:
        self._monotonic_clock = monotonic_clock
        self._latest: dict[WatchedFunction, MonotonicInstant] = {}
        self._first_look_at: MonotonicInstant | None = None

    def record_progress(self, function: WatchedFunction) -> None:
        """Records that ``function`` progressed now, such as the crawl on Kad at a search's end."""
        self._latest[function] = self._monotonic_clock.now()

    def time_without_progress(self, function: WatchedFunction) -> timedelta:
        """How long ``function`` has made no progress, counted from the first look at any
        function at the latest: the start before it, a reevaluation included, is no stall."""
        now = self._monotonic_clock.now()
        if self._first_look_at is None:
            self._first_look_at = now
        return now - self._latest.get(function, self._first_look_at)
