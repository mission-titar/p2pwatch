from datetime import UTC, datetime

from p2pwatch.adapters.driven.wall_clock_system import SystemWallClock


def test_now_reads_the_system_clock_in_utc() -> None:
    before = datetime.now(UTC)

    instant = SystemWallClock().now()

    assert before <= instant <= datetime.now(UTC)
    assert instant.tzinfo == UTC
