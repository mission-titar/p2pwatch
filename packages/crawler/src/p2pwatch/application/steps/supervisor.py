"""Runs each work's turns until the shutdown is requested, then cancels them all; a turn that raises
fails alone (spec v5 lot 4, D1 and D3)."""

import asyncio
from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.outcome import Bug, Outcome

# The least wait after a bug, so a bug before the client's own pacing never reruns at full speed:
# the client's start spacing, a starting value tuned at the release candidate.
FLOOR_AFTER_A_BUG = timedelta(seconds=60)


class ShutdownBoundArmer(Protocol):
    def __call__(self) -> None: ...


class Supervisor:
    """Runs the works it is given until the run state says the shutdown was requested."""

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
        """Runs each work's turns until the shutdown is requested, arms the bound, then cancels
        them all.

        A turn that raises fails alone, logged; a wait's error escapes as an ``ExceptionGroup``;
        the cancellation raises nothing."""
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self._run(work)) for work in works]
            await self._run_state_reader.wait_until_shutdown_requested()
            arm_shutdown_bound()
            # Every work, not only the searches: one asleep in its wait would hold the unwind
            # until the bound fires, and turn a clean stop into a forced one.
            for task in tasks:
                task.cancel()

    async def _run(self, work: Work) -> None:
        outcome = Outcome.success()
        while True:
            await self._wait(work, after=outcome)
            outcome = await self._outcome_of(work)
            # A yield that reads no clock: a turn that never suspends must not starve the loop.
            await asyncio.sleep(0)  # noqa: TID251

    async def _wait(self, work: Work, *, after: Outcome) -> None:
        """The work's own wait; after a bug, the later of it and the floor, never their sum."""
        if not isinstance(after.reason, Bug):
            await work.wait_for_next_turn()
            return
        async with asyncio.TaskGroup() as group:
            group.create_task(work.wait_for_next_turn())
            group.create_task(self._monotonic_clock.sleep(FLOOR_AFTER_A_BUG))

    async def _outcome_of(self, work: Work) -> Outcome:
        try:
            await work.run_once()
        except DeclaredFailure as failure:
            self._logger.warning("%s: %s", work, failure)
            return Outcome.declared(failure)
        except Exception as error:  # the work's boundary, by design: any other is a bug
            self._logger.exception("bug in %s", work, error=error)
            return Outcome.bug(repr(error))
        return Outcome.success()
