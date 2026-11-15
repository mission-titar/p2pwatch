"""Runs every task the node repeats, such as the status reading, until the shutdown is requested,
then cancels them all."""

import asyncio
from collections.abc import Sequence
from typing import Protocol

from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.steps.work import Work


class ShutdownBoundArmer(Protocol):
    def __call__(self) -> None: ...


class Supervisor:
    """Takes the turns of the works it is given until the run state says the shutdown was
    requested."""

    def __init__(self, *, run_state_reader: RunStateReader) -> None:
        self._run_state_reader = run_state_reader

    async def supervise(
        self,
        works: Sequence[Work],
        *,
        arm_shutdown_bound: ShutdownBoundArmer,
    ) -> None:
        """Takes each work's turns until the shutdown is requested, arms the bound, cancels them;
        a turn's exception escapes as an ``ExceptionGroup``, the cancellation raises none."""
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self._take_turns(work)) for work in works]
            await self._run_state_reader.wait_until_shutdown_requested()
            arm_shutdown_bound()
            # Every work, not only the searches: one asleep in its wait would hold the unwind
            # until the bound fires, and turn a clean stop into a forced one.
            for task in tasks:
                task.cancel()

    @staticmethod
    async def _take_turns(work: Work) -> None:
        while True:
            await work.wait_for_next_turn()
            await work.run_once()
            # Reads no clock: a turn that never suspends must not starve the other tasks.
            await asyncio.sleep(0)  # noqa: TID251
