from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.domain.persisted_wait import remaining_wait

_STARTED_AT = datetime(2026, 6, 12, tzinfo=UTC)
_DURATION = timedelta(seconds=300)


@pytest.mark.parametrize(
    ("elapsed", "remaining"),
    [
        (timedelta(0), _DURATION),
        (timedelta(seconds=100), timedelta(seconds=200)),
        (_DURATION, timedelta(0)),
    ],
)
def test_the_wait_left_is_the_duration_less_the_time_elapsed(
    elapsed: timedelta, remaining: timedelta
) -> None:
    assert remaining_wait(_STARTED_AT, _DURATION, _STARTED_AT + elapsed) == remaining


def test_a_start_in_the_future_leaves_the_whole_duration_and_no_more() -> None:
    # The wall clock stepped back while the node was down.
    assert remaining_wait(_STARTED_AT, _DURATION, _STARTED_AT - timedelta(hours=1)) == _DURATION


def test_a_wait_started_longer_ago_than_its_duration_is_over() -> None:
    assert remaining_wait(_STARTED_AT, _DURATION, _STARTED_AT + timedelta(days=2)) == timedelta(0)
