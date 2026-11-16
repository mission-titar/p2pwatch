"""Runs every task the node repeats, such as the status reading, until the shutdown is requested,
then cancels them all; a turn that raises fails alone, and the other works go on."""

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.expected_error import ExpectedError

# A bug that strikes at once would otherwise rerun at full speed, one trace per turn.
WAIT_AFTER_A_BUG = timedelta(seconds=60)


class ShutdownBoundArmer(Protocol):
    def __call__(self) -> None: ...


class Supervisor:
    """Takes the turns of the works it is given until the run state says the shutdown was
    requested."""

    def __init__(
        self,
        *,
        run_state_reader: RunStateReader,
        monotonic_clock: MonotonicClock,
        logger: Logger,
    ) -> None:
        self._run_state_reader = run_state_reader
        self._monotonic_clock = monotonic_clock
        self._logger = logger

    async def supervise(
        self,
        works: Sequence[Work],
        *,
        arm_shutdown_bound: ShutdownBoundArmer,
    ) -> None:
        """Takes each work's turns until the shutdown is requested, arms the bound, cancels them;
        a turn that raises fails alone, a wait's exception escapes as an ``ExceptionGroup``."""
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self._take_turns(work)) for work in works]
            await self._run_state_reader.wait_until_shutdown_requested()
            arm_shutdown_bound()
            # Every work, not only the searches: one asleep in its wait would hold the unwind
            # until the bound fires, and turn a clean stop into a forced one.
            for task in tasks:
                task.cancel()

    async def _take_turns(self, work: Work) -> None:
        met_a_bug = False
        while True:
            await self._wait(work, after_a_bug=met_a_bug)
            met_a_bug = await self._take_turn(work)
            # Reads no clock: a turn that never suspends must not starve the other tasks.
            await asyncio.sleep(0)  # noqa: TID251

    async def _wait(self, work: Work, *, after_a_bug: bool) -> None:
        """The work's own wait; after a bug, the later of it and ``WAIT_AFTER_A_BUG``."""
        if not after_a_bug:
            await work.wait_for_next_turn()
            return
        async with asyncio.TaskGroup() as group:
            group.create_task(work.wait_for_next_turn())
            group.create_task(self._monotonic_clock.sleep(WAIT_AFTER_A_BUG))

    async def _take_turn(self, work: Work) -> bool:
        """Takes one turn of ``work`` and returns whether it met a bug."""
        try:
            await work.run_once()
        except ExpectedError as error:  # aMule down, a search refused: no bug
            self._logger.warning("%s: %s", work, error)
        except Exception as error:  # the boundary of a turn, by design
            self._logger.exception("bug in %s", work, error=error)
            return True
        return False
