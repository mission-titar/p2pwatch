"""Runs each work's turns until the shutdown is requested, then cancels them all; a turn that raises
or passes its time limit fails alone, each turn's outcome recorded on the components its work feeds;
each restart the policy decides runs in a task of its own (spec v5 lot 4, D1, D3, D4, D5, D10)."""

import asyncio
from collections.abc import Coroutine, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.application.steps.health_recorder import HealthRecorder
from p2pwatch.application.steps.restart_policy import RestartPolicy
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
        restart_policy: RestartPolicy,
        logger: Logger,
    ) -> None:
        self._run_state_reader = run_state_reader
        self._monotonic_clock = monotonic_clock
        self._health_recorder = health_recorder
        self._restart_policy = restart_policy
        self._logger = logger
        self._group: asyncio.TaskGroup | None = None  # while the works run
        self._tasks: set[asyncio.Task[None]] = set()  # the works' and the restarts'
        self._works: dict[asyncio.Task[None], SupervisedWork] = {}

    async def supervise(
        self,
        works: Sequence[SupervisedWork],
        *,
        arm_shutdown_bound: ShutdownBoundArmer,
    ) -> None:
        """Runs each work's turns and the restarts until the shutdown is requested, arms the
        bound, then cancels them all.

        A turn that raises or passes its time limit fails alone, logged; a wait's error escapes
        as an ``ExceptionGroup``; the cancellation raises nothing."""
        async with asyncio.TaskGroup() as group:
            self._group = group
            try:
                for supervised in works:
                    self.add(supervised)
                self._start(self._restart_when_requested(group), group=group)
                await self._run_state_reader.wait_until_shutdown_requested()
                arm_shutdown_bound()
            finally:
                self._group = None
                # Every work, not only the searches: one asleep in its wait would hold the unwind
                # until the bound fires, and turn a clean stop into a forced one.
                for task in tuple(self._tasks):
                    task.cancel()

    def add(self, supervised: SupervisedWork) -> None:
        """Runs ``supervised``'s turns from now on, refused while no work runs."""
        if self._group is None:
            raise RuntimeError(f"{supervised.work}: added while no work runs")
        task = self._start(self._run(supervised), group=self._group)
        self._works[task] = supervised
        task.add_done_callback(self._works.pop)

    def _start(
        self, coroutine: Coroutine[object, object, None], *, group: asyncio.TaskGroup
    ) -> asyncio.Task[None]:
        task = group.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _restart_when_requested(self, group: asyncio.TaskGroup) -> None:
        """Starts each restart the policy requests in a task of its own, never in the turn whose
        outcome triggered it, which the restart cancels."""
        while True:
            owner = await self._restart_policy.requested()
            self._start(self._restart(owner), group=group)

    async def _restart(self, owner: StateOwner) -> None:
        """Stops the works feeding ``owner``'s components, then restarts it until it is rebuilt
        or the policy gives up, a floor after a bug between two tries; rebuilt, its components'
        bugs windows are emptied, their other windows kept."""
        components = self._restart_policy.components_of(owner)
        await self._stop_works_feeding(components)
        while True:
            try:
                await owner.restart()
            except Exception as error:  # the rebuild's boundary, by design
                self._logger.exception("restart of %s raised", owner, error=error)
                for component in components:
                    await self._health_recorder.record(
                        Outcome.bug(repr(error)), on=component, by=TURNS
                    )
                if not self._restart_policy.rebuild_raised(owner):
                    return
                await self._monotonic_clock.sleep(FLOOR_AFTER_A_BUG)
                continue
            # The new works start at the next suspension, after the windows are emptied.
            for component in components:
                component.empty_windows(of=TURNS)
            self._restart_policy.rebuilt(owner)
            self._logger.info("%s restarted", owner)
            return

    async def _stop_works_feeding(self, components: Sequence[Component]) -> None:
        stopping = [
            task
            for task, supervised in self._works.items()
            if not set(supervised.feeds).isdisjoint(components)
        ]
        for task in stopping:
            task.cancel()
        if stopping:
            await asyncio.wait(stopping)

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
