from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant


def test_two_instants_differ_by_a_timedelta() -> None:
    later, earlier = (
        MonotonicInstant(nanoseconds=5_000_000_000),
        MonotonicInstant(nanoseconds=2_000_000_000),
    )

    assert later - earlier == timedelta(seconds=3)
    assert earlier - later == timedelta(seconds=-3)


def test_a_difference_rounds_to_the_nearest_microsecond() -> None:
    assert MonotonicInstant(nanoseconds=1_600) - MonotonicInstant(nanoseconds=0) == timedelta(
        microseconds=2
    )
    assert MonotonicInstant(nanoseconds=0) - MonotonicInstant(nanoseconds=1_600) == timedelta(
        microseconds=-2
    )


def test_an_instant_mixes_with_no_wall_clock_instant() -> None:
    """Each ``type: ignore`` also proves mypy refuses the mix: an unused one fails the gate."""
    instant, wall = MonotonicInstant(nanoseconds=0), datetime(2026, 6, 12, tzinfo=UTC)

    with pytest.raises(TypeError):
        instant - wall  # type: ignore[operator]
    with pytest.raises(TypeError):
        wall - instant  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = instant < wall  # type: ignore[operator]
    with pytest.raises(TypeError):
        timedelta(0) + instant  # type: ignore[operator]
