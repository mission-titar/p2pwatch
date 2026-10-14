from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.ports.clock import MonotonicInstant, WallClock


class _StubWallClock:
    """Satisfies WallClock structurally (without importing it)."""

    def now(self) -> datetime:
        return datetime(2026, 6, 12, tzinfo=UTC)


def test_wall_clock_protocol_is_satisfied_structurally() -> None:
    wall_clock: WallClock = _StubWallClock()
    assert wall_clock.now() == datetime(2026, 6, 12, tzinfo=UTC)


def test_two_instants_differ_by_a_timedelta() -> None:
    later, earlier = MonotonicInstant(5_000_000_000), MonotonicInstant(2_000_000_000)

    assert later - earlier == timedelta(seconds=3)
    assert earlier - later == timedelta(seconds=-3)


def test_a_difference_rounds_to_the_nearest_microsecond() -> None:
    assert MonotonicInstant(1_600) - MonotonicInstant(0) == timedelta(microseconds=2)
    assert MonotonicInstant(0) - MonotonicInstant(1_600) == timedelta(microseconds=-2)


def test_an_instant_moves_by_a_timedelta_either_way() -> None:
    instant = MonotonicInstant(5_000_000_000)

    assert instant + timedelta(seconds=1) == MonotonicInstant(6_000_000_000)
    assert instant - timedelta(microseconds=1) == MonotonicInstant(4_999_999_000)


def test_instants_are_ordered() -> None:
    assert MonotonicInstant(1) < MonotonicInstant(2)
    assert max(MonotonicInstant(3), MonotonicInstant(2)) == MonotonicInstant(3)


def test_an_instant_mixes_with_no_wall_clock_instant() -> None:
    """Each ``type: ignore`` also proves mypy refuses the mix: an unused one fails the gate."""
    instant, wall = MonotonicInstant(0), datetime(2026, 6, 12, tzinfo=UTC)

    with pytest.raises(TypeError):
        instant - wall  # type: ignore[operator]
    with pytest.raises(TypeError):
        wall - instant  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = instant < wall  # type: ignore[operator]
    with pytest.raises(TypeError):
        timedelta(0) + instant  # type: ignore[operator]
