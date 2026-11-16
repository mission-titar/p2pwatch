"""Runs every task the node repeats, such as the status reading, until the shutdown is requested,
then cancels them all; a turn that raises or outlasts its time limit fails alone, the others go
on."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn, Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.expected_error import ExpectedError

# A bug that strikes at once would otherwise rerun at full speed, one trace per turn.
WAIT_AFTER_A_BUG = timedelta(seconds=60)


@dataclass(frozen=True, kw_only=True)
class SupervisedWork:
    """A work and its time limit, such as a search and its 25 min: the supervisor cuts a turn
    still running at its limit."""

    work: Work
    time_limit: timedelta

    def __post_init__(self) -> None:
        if self.time_limit <= timedelta(0):
            raise ValueError(f"{self.work}: a time limit must be positive, not {self.time_limit}")


class TurnTimeoutError(Exception):
    """A turn still running at its work's time limit, cut by the supervisor: a bug."""


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
        works: Sequence[SupervisedWork],
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

    async def _take_turns(self, supervised: SupervisedWork) -> None:
        met_a_bug = False
        while True:
            await self._wait(supervised.work, after_a_bug=met_a_bug)
            met_a_bug = await self._take_turn(supervised)

    async def _wait(self, work: Work, *, after_a_bug: bool) -> None:
        """The work's own wait; after a bug, the later of it and ``WAIT_AFTER_A_BUG``."""
        if not after_a_bug:
            await work.wait_for_next_turn()
            return
        async with asyncio.TaskGroup() as group:
            group.create_task(work.wait_for_next_turn())
            group.create_task(self._monotonic_clock.sleep(WAIT_AFTER_A_BUG))

    async def _take_turn(self, supervised: SupervisedWork) -> bool:
        """Takes one turn of the work and returns whether it met a bug."""
        work = supervised.work
        try:
            await self._within_time_limit(supervised)
        except ExpectedError as error:  # aMule down, a search refused: no bug
            self._logger.warning("%s: %s", work, error)
        except TurnTimeoutError:
            # No trace: it would show where the cut landed, not why the turn was slow.
            seconds = supervised.time_limit.total_seconds()
            self._logger.error("%s: past its time limit of %g s", work, seconds)
            return True
        except Exception as error:  # the boundary of a turn, by design
            self._logger.exception("bug in %s", work, error=error)
            return True
        return False

    async def _within_time_limit(self, supervised: SupervisedWork) -> None:
        """Takes the work's turn, cut by a ``TurnTimeoutError`` once its time limit has passed.

        The turn stays in the task that waited for it, so nothing runs between the wait and the
        turn; the race's end suspends, so even a turn that never does lets the other works run."""
        try:
            async with asyncio.TaskGroup() as race:
                expiry = race.create_task(self._expire(supervised.time_limit))
                try:
                    await supervised.work.run_once()
                finally:
                    expiry.cancel()
        except ExceptionGroup as raised:
            raise raised.exceptions[0] from None

    async def _expire(self, time_limit: timedelta) -> NoReturn:
        await self._monotonic_clock.sleep(time_limit)
        raise TurnTimeoutError
