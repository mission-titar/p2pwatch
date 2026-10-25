from datetime import UTC, datetime

import pytest

from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from tests.contracts.application.ports.driven.wall_clock_contract import WallClockContract


def test_now_reads_the_system_clock() -> None:
    before = datetime.now(UTC)

    instant = SystemWallClock().now()

    assert before <= instant <= datetime.now(UTC)


class TestSystemWallClock(WallClockContract):
    @pytest.fixture
    def wall_clock(self) -> SystemWallClock:
        return SystemWallClock()
