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
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.work_components import BUGS

# A bug that strikes at once would otherwise rerun at full speed, one trace per turn.
WAIT_AFTER_A_BUG = timedelta(seconds=60)


class TurnTimeoutError(Exception):
    """A turn still running at its work's time limit, cut by the supervisor: a bug."""


class ShutdownBoundArmer(Protocol):
    def __call__(self) -> None: ...


class HeldRestartable[R: Restartable[SupervisedWork]]:
    """The object a builder built latest, such as the notifier the next send goes to: the
    supervisor replaces it at each restart."""

    def __init__(self, first: R, *, builder: RestartableBuilder[R]) -> None:
        self._object = first
        self._builder = builder

    @property
    def builder(self) -> RestartableBuilder[R]:
        return self._builder

    def latest(self) -> R:
        """The object its builder built latest, such as the notifier the next send goes to."""
        return self._object

    async def _replace(self) -> Sequence[SupervisedWork]:
        """Closes the object, then holds the next its builder builds and returns its works; a
        build that raises leaves the closed one held, closed again by the next attempt."""
        await self._object.close()
        self._object = await self._builder.build()
        return self._object.works()

    async def _close(self) -> None:
        await self._object.close()


class Supervisor:
    """Takes the turns of the works it is given, and those of the objects a restart builds, until
    the run state says the shutdown was requested; holds the object each builder built latest."""

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
        # Each work's task while it runs, so a restart can stop the works over its object.
        self._running: dict[asyncio.Task[None], SupervisedWork] = {}
        self._held: dict[
            RestartableBuilder[Restartable[SupervisedWork]],
            HeldRestartable[Restartable[SupervisedWork]],
        ] = {}

    async def build_first[R: Restartable[SupervisedWork]](
        self, builder: RestartableBuilder[R]
    ) -> HeldRestartable[R]:
        """Has ``builder`` build its first object, such as the webui serving on its thread, and
        holds it: a restart replaces it, and ``close`` closes the one held then."""
        held = HeldRestartable(await builder.build(), builder=builder)
        self._held[builder] = held
        return held

    async def close(self) -> None:
        """Closes the object each builder built latest, the latest built first, as the shutdown
        does once every work has stopped; one that raises lets the others close."""
        async with AsyncExitStack() as closing:
            for held in self._held.values():
                closing.push_async_callback(held._close)

    async def supervise(
        self,
        works: Sequence[SupervisedWork],
        *,
        arm_shutdown_bound: ShutdownBoundArmer,
    ) -> None:
        """Takes each work's turns and runs each restart until the shutdown is requested, arms the
        bound, cancels them; a turn's exception fails it alone, a wait's escapes in a group."""
        async with asyncio.TaskGroup() as group:
            for supervised in works:
                self._add(supervised, group=group)
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

    def _add(self, supervised: SupervisedWork, *, group: asyncio.TaskGroup) -> None:
        task = group.create_task(self._take_turns(supervised))
        self._running[task] = supervised
        task.add_done_callback(self._running.pop)

    async def _restart_each_requested(self, group: asyncio.TaskGroup) -> None:
        async with asyncio.TaskGroup() as restarts:
            while True:
                request = await self._restart_requests.get()
                restarts.create_task(self._restart(request, group=group))

    async def _restart(self, request: RestartRequest, *, group: asyncio.TaskGroup) -> None:
        """Stops the works over the request's object, then closes it and has its builder build
        another; a rebuild that raises is tried again 60 s later, as long as the policy allows."""
        await self._stop_works_recorded_on(request.components)
        while not await self._rebuilt(request, group=group):
            if not request.rebuild_raised():
                return
            await self._monotonic_clock.sleep(WAIT_AFTER_A_BUG)

    async def _stop_works_recorded_on(self, components: Sequence[Component]) -> None:
        stopping = [
            task
            for task, supervised in self._running.items()
            if not set(supervised.components).isdisjoint(components)
        ]
        for task in stopping:
            task.cancel()
        for task in stopping:  # awaited, so no turn runs on the old object once it is rebuilt
            await asyncio.wait((task,))

    async def _rebuilt(self, request: RestartRequest, *, group: asyncio.TaskGroup) -> bool:
        """Closes the request's object, holds the one its builder builds next and runs the works
        over it; whether it was built, a rebuild that raised recorded as a bug on each part."""
        builder = request.builder
        try:
            works = await self._held[builder]._replace()
        except ExpectedError as error:  # aMule refusing the new login's password
            self._logger.warning("rebuild of %s: %s", builder, error)
        except Exception as error:  # the boundary of a rebuild, by design
            self._logger.exception("bug in the rebuild of %s", builder, error=error)
        else:
            request.rebuilt()
            self._logger.info("%s rebuilt", builder)
            for supervised in works:
                self._add(supervised, group=group)
            return True
        for component in request.components:
            await self._node_health.record(on=component, rule=BUGS, detected=True)
        return False

    async def _take_turns(self, supervised: SupervisedWork) -> None:
        met_a_bug = False
        while True:
            await self._wait(supervised.work, after_a_bug=met_a_bug)
            met_a_bug = await self._take_turn(supervised)
            for component in supervised.components:
                await self._node_health.record(on=component, rule=BUGS, detected=met_a_bug)

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
