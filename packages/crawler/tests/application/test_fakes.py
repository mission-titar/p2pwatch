"""``FakeTime``: the clock step the monotonic clock's tests rely on; ``FakeLogger``: its lines."""

from datetime import timedelta

import pytest

from p2pwatch_testing.application.fakes import FakeLogger, FakeTime, LoggedLine


def test_a_wall_clock_step_leaves_the_monotonic_clock() -> None:
    fake_time = FakeTime()
    wall_before, monotonic_before = fake_time.wall.now(), fake_time.monotonic.now()

    fake_time.step_wall(timedelta(hours=-1))

    assert fake_time.wall.now() == wall_before - timedelta(hours=1)
    assert fake_time.monotonic.now() == monotonic_before


@pytest.mark.asyncio
async def test_a_monotonic_sleep_records_its_duration_and_moves_both_clocks() -> None:
    fake_time = FakeTime()
    wall_before, monotonic_before = fake_time.wall.now(), fake_time.monotonic.now()

    await fake_time.monotonic.sleep(timedelta(seconds=60))

    assert fake_time.sleeps == [timedelta(seconds=60)]
    assert fake_time.wall.now() == wall_before + timedelta(seconds=60)
    assert fake_time.monotonic.now() == monotonic_before + timedelta(seconds=60)


def test_a_logged_line_keeps_its_level_and_its_formatted_message() -> None:
    logger = FakeLogger()

    logger.info("searched '%s'", "keroro")
    logger.warning("backoff %.1fs", 2.0)
    logger.error("100% lost")

    assert logger.lines == [
        LoggedLine("info", "searched 'keroro'"),
        LoggedLine("warning", "backoff 2.0s"),
        LoggedLine("error", "100% lost"),  # no argument: kept as written, as logging does
    ]
