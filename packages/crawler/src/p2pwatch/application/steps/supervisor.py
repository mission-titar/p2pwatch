"""Runs each work's turns until the shutdown is requested, then cancels them all; a turn that raises
or passes its time limit fails alone, each turn's outcome recorded on the components its work feeds
(spec v5 lot 4, D1, D3, D4 and D10)."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.work import Work
from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.outcome import TURNS, Bug, Outcome

# The least wait after a bug, so a bug before the client's own pacing never reruns at full speed:
# the client's start spacing, a starting value tuned at the release candidate.
FLOOR_AFTER_A_BUG = timedelta(seconds=60)


@dataclass(frozen=True, kw_only=True)
class SupervisedWork:
    """A work, its time limit, past which a turn is cut as a bug (spec v5 lot 4, D4), and the
    components its turns' outcomes feed, each reading them."""

    work: Work
    time_limit: timedelta
    feeds: tuple[Component, ...]

    def __post_init__(self) -> None:
        if self.time_limit <= timedelta(0):
            raise ValueError(f"{self.work}: a time limit must be positive, not {self.time_limit}")
        if not self.feeds or not all(component.reads(TURNS) for component in self.feeds):
            raise ValueError(f"{self.work}: a component at least expected, each reading its turns")


class TurnPastItsLimit(Exception):
    """A turn cut at its work's time limit, recorded as a bug."""


class ShutdownBoundArmer(Protocol):
    def __call__(self) -> None: ...


class Supervisor:
    """Runs the works it is given until the run state says the shutdown was requested."""

    def __init__(
        self,
        *,
        run_state_reader: RunStateReader,
        monotonic_clock: MonotonicClock,
        health_recorder: HealthRecorder,
        logger: Logger,
    ) -> None:
        self._run_state_reader = run_state_reader
        self._monotonic_clock = monotonic_clock
        self._health_recorder = health_recorder
        self._logger = logger

    async def supervise(
        self,
        works: Sequence[SupervisedWork],
        *,
        arm_shutdown_bound: ShutdownBoundArmer,
    ) -> None:
        """Runs each work's turns until the shutdown is requested, arms the bound, then cancels
        them all.

        A turn that raises or passes its time limit fails alone, logged; a wait's error escapes
        as an ``ExceptionGroup``; the cancellation raises nothing."""
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(self._run(work)) for work in works]
            await self._run_state_reader.wait_until_shutdown_requested()
            arm_shutdown_bound()
            # Every work, not only the searches: one asleep in its wait would hold the unwind
            # until the bound fires, and turn a clean stop into a forced one.
            for task in tasks:
                task.cancel()

    async def _run(self, supervised: SupervisedWork) -> None:
        outcome = Outcome.success()
        while True:
            await self._wait(supervised.work, after=outcome)
            outcome = await self._outcome_of(supervised)
            for component in supervised.feeds:
                await self._health_recorder.record(outcome, on=component, by=TURNS)

    async def _wait(self, work: Work, *, after: Outcome) -> None:
        """The work's own wait; after a bug, the later of it and the floor, never their sum."""
        if not isinstance(after.reason, Bug):
            await work.wait_for_next_turn()
            return
        async with asyncio.TaskGroup() as group:
            group.create_task(work.wait_for_next_turn())
            group.create_task(self._monotonic_clock.sleep(FLOOR_AFTER_A_BUG))

    async def _outcome_of(self, supervised: SupervisedWork) -> Outcome:
        work = supervised.work
        try:
            await self._within_its_limit(supervised)
        except DeclaredFailure as failure:
            self._logger.warning("%s: %s", work, failure)
            return Outcome.declared(failure)
        except TurnPastItsLimit:
            # No trace: it would show where the cancellation landed, not why the turn was slow.
            self._logger.error("%s: past its time limit of %s", work, supervised.time_limit)
            return Outcome.bug(f"past its time limit of {supervised.time_limit}")
        except Exception as error:  # the work's boundary, by design: any other is a bug
            self._logger.exception("bug in %s", work, error=error)
            return Outcome.bug(repr(error))
        return Outcome.success()

    async def _within_its_limit(self, supervised: SupervisedWork) -> None:
        """The work's turn raced against its time limit, the loser cancelled.

        The turn runs in the task that waited for it, so nothing runs between the wait's end and
        the turn's start; the race's end suspends even a turn that never does."""
        try:
            async with asyncio.TaskGroup() as group:
                expiry = group.create_task(self._expire(supervised.time_limit))
                try:
                    await supervised.work.run_once()
                finally:
                    expiry.cancel()
        except ExceptionGroup as failures:
            raise failures.exceptions[0] from None

    async def _expire(self, time_limit: timedelta) -> None:
        await self._monotonic_clock.sleep(time_limit)
        raise TurnPastItsLimit
