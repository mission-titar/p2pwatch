"""The interval a page reads (source points spec, D6): its parsing, its 7-day cut, its shifts."""

from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.adapters.driving.webui.interval import Interval, parse_instant, requested_interval

pytestmark = pytest.mark.usefixtures("close_test_connections")

_NOW = datetime(2026, 10, 14, 20, 0, tzinfo=UTC)
_DAY = timedelta(days=1)


@pytest.mark.parametrize(
    "raw",
    [
        "2026-10-06 12:00:00Z",
        "2026-10-06T12:00",
        "2026-10-06T12:00:00.999999",
        "2026-10-06T14:00:00+02:00",
        " 2026-10-06 12:00:00Z ",
    ],
    ids=["webui-format", "datetime-local", "fraction", "offset", "spaces"],
)
def test_an_instant_is_read_as_utc_to_the_second(raw: str) -> None:
    assert parse_instant(raw) == datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "raw",
    [None, "", "yesterday", "1969-12-31T23:59:59Z", "0001-01-01T00:00:00+01:00"],
    ids=["absent", "empty", "malformed", "before-the-epoch", "overflowing"],
)
def test_an_instant_absent_malformed_or_before_the_epoch_is_none(raw: str | None) -> None:
    assert parse_instant(raw) is None


def test_an_interval_up_to_7_days_is_kept() -> None:
    raw_from, raw_to = "2026-10-01 00:00:00Z", "2026-10-04 00:00:00Z"
    interval = Interval(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 4, tzinfo=UTC))
    assert requested_interval(raw_from, raw_to, _NOW) == interval
    week = requested_interval("2026-10-01 00:00:00Z", "2026-10-08 00:00:00Z", _NOW)
    assert week == Interval(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 8, tzinfo=UTC))


def test_an_interval_past_7_days_keeps_the_7_ending_at_its_to() -> None:
    to = datetime(2026, 10, 1, tzinfo=UTC)
    interval = requested_interval("2026-09-01 00:00:00Z", "2026-10-01 00:00:00Z", _NOW)
    assert interval == Interval(to - 7 * _DAY, to, clamped=True)
    second_more = requested_interval("2026-09-23 23:59:59Z", "2026-10-01 00:00:00Z", _NOW)
    assert second_more == Interval(to - 7 * _DAY, to, clamped=True)


def test_a_missing_to_is_now_and_a_missing_from_is_7_days_before_to() -> None:
    to = datetime(2026, 10, 1, tzinfo=UTC)
    assert requested_interval(None, "2026-10-01 00:00:00Z", _NOW) == Interval(to - 7 * _DAY, to)
    since = _NOW - 2 * _DAY
    assert requested_interval("2026-10-12 20:00:00Z", None, _NOW) == Interval(since, _NOW)


@pytest.mark.parametrize("raw_from", ["2026-10-01 00:00:00Z", "2026-10-02 00:00:00Z", "nope"])
def test_a_from_not_before_to_counts_as_absent(raw_from: str) -> None:
    to = datetime(2026, 10, 1, tzinfo=UTC)
    interval = requested_interval(raw_from, "2026-10-01 00:00:00Z", _NOW)
    assert interval == Interval(to - 7 * _DAY, to)


def test_a_cut_interval_shifts_by_the_7_days_it_shows_and_is_no_longer_cut() -> None:
    to = datetime(2026, 10, 1, tzinfo=UTC)
    assert Interval(to - 7 * _DAY, to, clamped=True).shifted(1) == Interval(to, to + 7 * _DAY)
