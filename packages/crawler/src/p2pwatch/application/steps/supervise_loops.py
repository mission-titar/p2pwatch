"""Runs the crawler's loops until the shutdown is requested, then cancels them all."""

import asyncio
from collections.abc import Callable, Coroutine, Sequence

from p2pwatch.application.ports.driven.run_state_reader import RunStateReader


async def supervise_loops(
    loops: Sequence[Callable[[], Coroutine[object, object, None]]],
    *,
    run_state_reader: RunStateReader,
    arm_shutdown_bound: Callable[[], None],
) -> None:
    """Run each loop until the shutdown is requested, call ``arm_shutdown_bound``, then cancel and
    unwind them.

    A loop's own failure escapes as an ``ExceptionGroup``; the cancellation itself raises nothing.
    """
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(loop()) for loop in loops]
        await run_state_reader.wait_until_shutdown_requested()
        arm_shutdown_bound()
        # Every loop, not only the searches: one asleep in its cycle would hold the unwind until
        # the bound fires, and turn a clean stop into a forced one.
        for task in tasks:
            task.cancel()
