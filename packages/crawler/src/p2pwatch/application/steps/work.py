"""``Work``: what the supervisor runs again and again, one turn a call to ``run_once()``."""

import asyncio
from abc import ABC, abstractmethod


class Work(ABC):
    """A turn and the wait before it, the first included, computed from the work's own state."""

    @abstractmethod
    async def run_once(self) -> None:
        """Takes one turn."""

    @abstractmethod
    async def wait_for_next_turn(self) -> None:
        """Returns once the next turn may start."""

    async def run(self) -> None:
        """Waits, takes its turn and yields, until cancelled; a turn's error ends it."""
        while True:
            await self.wait_for_next_turn()
            await self.run_once()
            # A yield that reads no clock: a turn that never suspends must not starve the loop.
            await asyncio.sleep(0)  # noqa: TID251
