"""The interval a page reads (source points spec, D6): its 7-day cut, its shifts."""

from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.domain.interval import Interval, requested_interval

_NOW = datetime(2026, 10, 14, 20, 0, tzinfo=UTC)
_DAY = timedelta(days=1)


def _day(day: int, month: int = 10) -> datetime:
    return datetime(2026, month, day, tzinfo=UTC)


def test_an_interval_up_to_7_days_is_kept() -> None:
    assert requested_interval(_day(1), requested_until=_day(4), now=_NOW) == Interval(
        _day(1), _day(4)
    )
    assert requested_interval(_day(1), requested_until=_day(8), now=_NOW) == Interval(
        _day(1), _day(8)
    )


def test_an_interval_past_7_days_keeps_the_7_ending_at_its_to() -> None:
    to = _day(1)
    interval = requested_interval(_day(1, month=9), requested_until=to, now=_NOW)
    assert interval == Interval(to - 7 * _DAY, to, clamped=True)
    second_more = requested_interval(
        datetime(2026, 9, 23, 23, 59, 59, tzinfo=UTC), requested_until=to, now=_NOW
    )
    assert second_more == Interval(to - 7 * _DAY, to, clamped=True)


def test_a_missing_to_is_now_and_a_missing_from_is_7_days_before_to() -> None:
    to = _day(1)
    assert requested_interval(None, requested_until=to, now=_NOW) == Interval(to - 7 * _DAY, to)
    since = _NOW - 2 * _DAY
    assert requested_interval(since, requested_until=None, now=_NOW) == Interval(since, _NOW)


@pytest.mark.parametrize("since", [_day(1), _day(2)], ids=["at-to", "after-to"])
def test_a_from_not_before_to_counts_as_absent(since: datetime) -> None:
    to = _day(1)
    assert requested_interval(since, requested_until=to, now=_NOW) == Interval(to - 7 * _DAY, to)


def test_a_cut_interval_shifts_by_the_7_days_it_shows_and_is_no_longer_cut() -> None:
    to = datetime(2026, 10, 1, tzinfo=UTC)
    assert Interval(to - 7 * _DAY, to, clamped=True).shifted(1) == Interval(to, to + 7 * _DAY)
