"""The promise of the ``WallClock`` port."""

import asyncio
from abc import ABC, abstractmethod
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.wall_clock import WallClock


class WallClockContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def wall_clock(self) -> WallClock:
        """A clock read on the test's running loop and from a thread."""

    async def test_now_is_aware_in_utc(self, wall_clock: WallClock) -> None:
        assert wall_clock.now().utcoffset() == timedelta(0)

    async def test_now_is_read_from_a_thread_with_no_running_loop(
        self, wall_clock: WallClock
    ) -> None:
        from_thread = await asyncio.to_thread(wall_clock.now)

        assert from_thread.utcoffset() == timedelta(0)
