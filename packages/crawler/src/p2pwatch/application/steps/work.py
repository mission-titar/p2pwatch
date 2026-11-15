"""``Work``: a task the node repeats, such as reading aMule's status every minute."""

import asyncio
from abc import ABC, abstractmethod


class Work(ABC):
    """A task the node repeats: a wait, then a turn, again; the first turn waits too, each work
    computing its wait from its own state."""

    @abstractmethod
    async def wait_for_next_turn(self) -> None:
        """Returns once the next turn may start, at once if it already may."""

    @abstractmethod
    async def run_once(self) -> None:
        """Takes one turn, such as one reading of aMule's status."""

    async def run(self) -> None:
        """Waits and takes a turn, again and again, until cancelled or a turn raises."""
        while True:
            await self.wait_for_next_turn()
            await self.run_once()
            # Reads no clock: a turn that never suspends must not starve the other tasks.
            await asyncio.sleep(0)  # noqa: TID251
