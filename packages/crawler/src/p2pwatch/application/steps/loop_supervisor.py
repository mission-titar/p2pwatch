"""Runs the crawler's loops until the shutdown is requested, then cancels them all."""

import asyncio
from collections.abc import Callable, Coroutine, Sequence

from p2pwatch.application.ports.driven.run_state_reader import RunStateReader


class LoopSupervisor:
    """Runs the loops it is given until the run state says the shutdown was requested."""

    def __init__(self, *, run_state_reader: RunStateReader) -> None:
        self._run_state_reader = run_state_reader

    async def supervise(
        self,
        loops: Sequence[Callable[[], Coroutine[object, object, None]]],
        *,
        arm_shutdown_bound: Callable[[], None],
    ) -> None:
        """Runs each loop until the shutdown is requested, arms the bound, then cancels them all.

        A loop's own failure escapes as an ``ExceptionGroup``; the cancellation raises nothing."""
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(loop()) for loop in loops]
            await self._run_state_reader.wait_until_shutdown_requested()
            arm_shutdown_bound()
            # Every loop, not only the searches: one asleep in its cycle would hold the unwind
            # until the bound fires, and turn a clean stop into a forced one.
            for task in tasks:
                task.cancel()
