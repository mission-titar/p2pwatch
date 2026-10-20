from datetime import UTC, datetime

from p2pwatch.ports.driven.clock import WallClock


class _StubWallClock:
    """Satisfies WallClock structurally (without importing it)."""

    def now(self) -> datetime:
        return datetime(2026, 6, 12, tzinfo=UTC)


def test_wall_clock_protocol_is_satisfied_structurally() -> None:
    wall_clock: WallClock = _StubWallClock()
    assert wall_clock.now() == datetime(2026, 6, 12, tzinfo=UTC)
