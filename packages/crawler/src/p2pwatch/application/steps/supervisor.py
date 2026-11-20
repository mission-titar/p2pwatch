"""Runs every task the node repeats, such as the status reading, until the shutdown is requested,
then cancels them all; a turn that raises or outlasts its time limit fails alone, the others go
on, and whether it met a bug is recorded on the parts it is about. It also holds the objects the
node can restart, such as the aMule client, and restarts one when the restart policy asks."""

import asyncio
from collections.abc import Sequence
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import NoReturn, Protocol

from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.restart_policy import RestartRequest
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.work_dependencies import BUGS

# A bug that strikes at once would otherwise rerun at full speed, one trace per turn.
WAIT_AFTER_A_BUG = timedelta(seconds=60)


class TurnTimeoutError(Exception):
    """A turn still running at its work's time limit, cut by the supervisor: a bug."""


class ShutdownBoundArmer(Protocol):
    def __call__(self) -> None: ...


class SupervisedObject:
    """The supervisor's record of one object it rebuilds, such as the aMule client: its builder
    and the latest object it built."""

    def __init__(
        self, builder: RestartableBuilder[SupervisedWork], *, first: Restartable[SupervisedWork]
    ) -> None:
        self.builder = builder
        self.latest = first

    async def rebuild(self) -> Sequence[SupervisedWork]:
        """Closes the latest object, holds the one its builder builds next and returns its works;
        a build that raises leaves the closed one held, closed again by the next attempt."""
        await self.latest.close()
        self.latest = await self.builder.build()
        return self.latest.works()


class Supervisor:
    """Takes the turns of the works of each object it built, until the run state says the shutdown
    was requested; holds the object each builder built latest, and rebuilds it."""

    def __init__(
        self,
        *,
        run_state_reader: RunStateReader,
        monotonic_clock: MonotonicClock,
        node_health: NodeHealth,
        logger: Logger,
    ) -> None:
        self._run_state_reader = run_state_reader
        self._monotonic_clock = monotonic_clock
        self._node_health = node_health
        self._logger = logger
        self._restart_requests: asyncio.Queue[RestartRequest] = asyncio.Queue()
        # Each work's task while it runs, and the object it is over, which a restart stops it with.
        self._running: dict[asyncio.Task[None], SupervisedObject] = {}
        self._objects: dict[RestartableBuilder[SupervisedWork], SupervisedObject] = {}

    async def build_first(
        self, builder: RestartableBuilder[SupervisedWork]
    ) -> Sequence[SupervisedWork]:
        """Has ``builder`` build its first object, such as the webui serving on its thread, holds
        it until a rebuild or the shutdown, and returns the works ``supervise`` runs over it."""
        first = await builder.build()
        self._objects[builder] = SupervisedObject(builder, first=first)
        return first.works()

    async def close(self) -> None:
        """Closes the object each builder built latest, the latest built first, as the shutdown
        does once every work has stopped; one that raises lets the others close."""
        async with AsyncExitStack() as closing:
            for supervised in self._objects.values():
                closing.push_async_callback(supervised.latest.close)

    async def supervise(self, *, arm_shutdown_bound: ShutdownBoundArmer) -> None:
        """Takes the turns of each object's works and runs each restart until the shutdown is
        requested, arms the bound, cancels them; a wait's exception escapes in a group."""
        async with asyncio.TaskGroup() as group:
            for supervised in self._objects.values():
                for work in supervised.latest.works():
                    self._add(work, over=supervised, group=group)
            restarts = group.create_task(self._restart_each_requested(group))
            await self._run_state_reader.wait_until_shutdown_requested()
            arm_shutdown_bound()
            restarts.cancel()
            # Every work, not only the searches: one asleep in its wait would hold the unwind
            # until the bound fires, and turn a clean stop into a forced one.
            for task in tuple(self._running):
                task.cancel()

    def restart(self, request: RestartRequest) -> None:
        """Restarts the request's object, such as the aMule client, in a task of its own: never in
        the turn that asked for it, which the restart stops."""
        self._restart_requests.put_nowait(request)

    def _add(
        self, supervised: SupervisedWork, *, over: SupervisedObject, group: asyncio.TaskGroup
    ) -> None:
        task = group.create_task(self._take_turns(supervised))
        self._running[task] = over
        task.add_done_callback(self._running.pop)

    async def _restart_each_requested(self, group: asyncio.TaskGroup) -> None:
        async with asyncio.TaskGroup() as restarts:
            while True:
                request = await self._restart_requests.get()
                restarts.create_task(self._restart(request, group=group))

    async def _restart(self, request: RestartRequest, *, group: asyncio.TaskGroup) -> None:
        """Stops the works over the request's object, then closes it and has its builder build
        another; a rebuild that raises is tried again 60 s later, as long as the policy allows."""
        await self._stop_works_over(self._objects[request.builder])
        while not await self._rebuilt(request, group=group):
            if not request.rebuild_raised():
                return
            await self._monotonic_clock.sleep(WAIT_AFTER_A_BUG)

    async def _stop_works_over(self, supervised: SupervisedObject) -> None:
        stopping = [task for task, over in self._running.items() if over is supervised]
        for task in stopping:
            task.cancel()
        for task in stopping:  # awaited, so no turn runs on the old object once it is rebuilt
            await asyncio.wait((task,))

    async def _rebuilt(self, request: RestartRequest, *, group: asyncio.TaskGroup) -> bool:
        """Has the request's object rebuilt and runs the works over the new one; whether it was, a
        rebuild that raised recorded as a bug on each of its parts."""
        builder = request.builder
        supervised = self._objects[builder]
        try:
            works = await supervised.rebuild()
        except ExpectedError as error:  # aMule refusing the new login's password
            self._logger.warning("rebuild of %s: %s", builder, error)
        except Exception as error:  # the boundary of a rebuild, by design
            self._logger.exception("bug in the rebuild of %s", builder, error=error)
        else:
            request.rebuilt()
            self._logger.info("%s rebuilt", builder)
            for work in works:
                self._add(work, over=supervised, group=group)
            return True
        for dependency in request.dependencies:
            await self._node_health.record(on=dependency, rule=BUGS, detected=True)
        return False

    async def _take_turns(self, supervised: SupervisedWork) -> None:
        met_a_bug = False
        while True:
            await self._wait(supervised.work, after_a_bug=met_a_bug)
            met_a_bug = await self._take_turn(supervised)
            for dependency in supervised.dependencies:
                await self._node_health.record(on=dependency, rule=BUGS, detected=met_a_bug)

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
        """Takes the work's turn, cancelled past its time limit and raised as ``TurnTimeoutError``;
        its end always suspends, so a turn that never awaits still lets the other works run."""
        raised: Exception | None = None
        try:
            async with asyncio.TaskGroup() as race:
                expiry = race.create_task(self._expire(supervised.time_limit))
                try:
                    await supervised.work.run_once()
                except Exception as error:  # kept out of the group, which would wrap it
                    raised = error
                finally:
                    expiry.cancel()
        except ExceptionGroup as expired:
            raise expired.exceptions[0] from None
        if raised is not None:
            raise raised

    async def _expire(self, time_limit: timedelta) -> NoReturn:
        await self._monotonic_clock.sleep(time_limit)
        raise TurnTimeoutError
