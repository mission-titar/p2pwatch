"""``FakeTime``: the clock step the tests of the monotonic clock rely on."""

from datetime import timedelta

import pytest

from tests.application.fakes import FakeTime


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
