"""Runs every task the node repeats, such as the status reading, the works of the objects it
built, until the shutdown is requested, then cancels them all; a turn that raises or outlasts its
time limit fails alone, the others go on. It judges each work on its own turns, and rebuilds the
object, such as the aMule client, one of whose works keeps meeting bugs, waiting longer each time;
its third rebuild in vain leaves it unrepaired, and a function of the crawler wholly lost, such as
the crawl, every search failing, ends the supervision with a ``CrawlerRestartError``."""

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
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.domain.crawler_function import CrawlerFunction
from p2pwatch.domain.crawler_restart_error import CrawlerRestartError
from p2pwatch.domain.expected_error import ExpectedError
from p2pwatch.domain.health.health_rule import Detections, HealthRule, HealthState

# A bug that strikes at once would otherwise rerun at full speed, one trace per turn.
WAIT_AFTER_A_BUG = timedelta(seconds=60)

# One bug now and then fails its turn alone: three turns in a row of one work rebuild its object.
BUGS = HealthRule(
    name="bugs",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)

# Past three, nothing tells a work's own bug from a shared state but a crawler restart: the object
# is left unrepaired, and the crawler restarts only once a function is wholly lost.
REBUILDS_IN_VAIN_AT_MOST = 3

# Doubled after each rebuild in vain, 1, 2, then 4 min, as Kubernetes' CrashLoopBackOff waits.
FIRST_WAIT_BEFORE_A_REBUILD = timedelta(minutes=1)


class TurnTimeoutError(Exception):
    """A turn still running at its work's time limit, cut by the supervisor: a bug."""


class ShutdownBoundArmer(Protocol):
    def __call__(self) -> None: ...


class _WorkTurns:
    """Whether each latest turn of one work met a bug, such as a search's, kept across its
    object's rebuilds, and its turns since the latest."""

    def __init__(self, function: CrawlerFunction | None) -> None:
        self.function = function
        self.bugs = HealthState.UNKNOWN
        self._latest_met_a_bug: tuple[bool, ...] = ()
        self._since_build: tuple[bool, ...] = ()

    def record(self, *, met_a_bug: bool) -> HealthState:
        """Counts one turn and returns its bugs' state before it."""
        previous = self.bugs
        self._latest_met_a_bug = (*self._latest_met_a_bug, met_a_bug)[-BUGS.checks_kept :]
        self._since_build = (*self._since_build, met_a_bug)[-BUGS.fails_at.among_last :]
        self.bugs = BUGS.state_after(self._latest_met_a_bug, previous=previous)
        return previous

    def failing_since_build(self) -> bool:
        """Whether its turns since its object's latest build alone fail, 3 bugs in a row."""
        state = BUGS.state_after(self._since_build, previous=HealthState.UNKNOWN)
        return state is HealthState.FAILING

    def rebuilt(self) -> None:
        self._since_build = ()


class SupervisedObject:
    """The supervisor's record of one object it rebuilds, such as the aMule client: its builder, the
    latest object built, whether each latest turn of each of its works met a bug, its rebuilds in
    vain, the third leaving it unrepaired."""

    def __init__(
        self,
        builder: RestartableBuilder[SupervisedWork],
        *,
        first: Restartable[SupervisedWork],
        logger: Logger,
    ) -> None:
        self.builder = builder
        self.latest = first
        self._logger = logger
        # Each work's, by its name in the log: a work built anew is the same work.
        self._works: dict[str, _WorkTurns] = {}
        self._hold(first.works())
        # Rebuilt since its works were last all healthy: one failing again counts in vain.
        self._rebuilt = False
        # A rebuild decided: the last turns of the works it stops decide nothing.
        self._works_stopped = False
        self._in_vain = 0

    @property
    def unrepaired(self) -> bool:
        """Whether its third rebuild in vain left it so: rebuilt no more until every work of it that
        turned failing is healthy again."""
        return self._in_vain >= REBUILDS_IN_VAIN_AT_MOST

    def states_of(self, function: CrawlerFunction) -> list[HealthState]:
        """The bugs' state of each of its works serving ``function``, each failing while it holds no
        work, its third rebuild having raised."""
        lost = self.unrepaired and self._works_stopped
        return [
            HealthState.FAILING if lost else turns.bugs
            for turns in self._works.values()
            if turns.function is function
        ]

    def record_turn(self, supervised: SupervisedWork, *, met_a_bug: bool) -> bool:
        """Counts one turn of one of its works, such as a search that met a bug; whether a rebuild
        is decided, which stops its works."""
        turns = self._works[str(supervised.work)]
        previous = turns.record(met_a_bug=met_a_bug)
        if self._works_stopped:
            return False
        if previous is HealthState.FAILING and not self._failing():
            self._rebuilt, self._in_vain = False, 0
            return False
        if self.unrepaired:
            return False
        if not self._rebuilt:
            if turns.bugs is not HealthState.FAILING:
                return False
            self._rebuilt = self._works_stopped = True
            self._logger.warning("restarting %s: bugs in its works", self.builder)
            return True
        if not turns.failing_since_build():
            return False
        self.count_in_vain()
        if self.unrepaired:
            return False
        self._works_stopped = True
        in_vain = f"{self._in_vain} of {REBUILDS_IN_VAIN_AT_MOST} rebuilds in vain"
        message = "restarting %s again, %s: bugs in its works"
        self._logger.warning(message, self.builder, in_vain)
        return True

    def _failing(self) -> bool:
        return any(turns.bugs is HealthState.FAILING for turns in self._works.values())

    def count_in_vain(self) -> None:
        """Counts one rebuild in vain, such as one that raised."""
        self._in_vain += 1

    def wait_before_rebuild(self) -> timedelta:
        """How long its next rebuild waits once its works stopped: 1 min, doubled after each
        rebuild in vain."""
        return FIRST_WAIT_BEFORE_A_REBUILD * (1 << self._in_vain)

    async def rebuild(self) -> Sequence[SupervisedWork]:
        """Closes the latest object, holds the one its builder builds next and returns its works,
        each work's turns kept; a build that raises leaves the closed one held."""
        await self.latest.close()
        self.latest = await self.builder.build()
        works = self.latest.works()
        self._hold(works)
        for turns in self._works.values():
            turns.rebuilt()
        self._works_stopped = False
        return works

    def _hold(self, works: Sequence[SupervisedWork]) -> None:
        for supervised in works:
            self._works.setdefault(str(supervised.work), _WorkTurns(supervised.function))


class Supervisor:
    """Takes the turns of the works of each object it built, until the run state says the shutdown
    was requested; holds the object each builder built latest, and rebuilds it when one of its
    works keeps meeting bugs, three times in vain at most."""

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
        self._rebuilds_decided: asyncio.Queue[SupervisedObject] = asyncio.Queue()
        # Each work's task while it runs, and the object it is over, which a rebuild stops it with.
        self._running: dict[asyncio.Task[None], SupervisedObject] = {}
        self._objects: dict[RestartableBuilder[SupervisedWork], SupervisedObject] = {}
        # A function of the crawler wholly lost, which ends the supervision.
        self._restarts_decided: asyncio.Queue[CrawlerRestartError] = asyncio.Queue()

    async def build_first(
        self, builder: RestartableBuilder[SupervisedWork]
    ) -> Sequence[SupervisedWork]:
        """Has ``builder`` build its first object, such as the webui serving on its thread, holds
        it until a rebuild or the shutdown, and returns the works ``supervise`` runs over it."""
        first = await builder.build()
        self._objects[builder] = SupervisedObject(builder, first=first, logger=self._logger)
        return first.works()

    async def close(self) -> None:
        """Closes the object each builder built latest, the latest built first, as the shutdown
        does once every work has stopped; one that raises lets the others close."""
        async with AsyncExitStack() as closing:
            for supervised in self._objects.values():
                closing.push_async_callback(supervised.latest.close)

    async def supervise(self, *, arm_shutdown_bound: ShutdownBoundArmer) -> None:
        """Takes the turns of each object's works and runs each rebuild until the shutdown is
        requested or a function is wholly lost, arms the bound, cancels them, then raises the
        latter's ``CrawlerRestartError``; a wait's exception escapes in a group."""
        async with asyncio.TaskGroup() as group:
            for supervised in self._objects.values():
                for work in supervised.latest.works():
                    self._add(work, over=supervised, group=group)
            rebuilds = group.create_task(self._rebuild_each_decided(group))
            restart = group.create_task(self._restarts_decided.get())
            requested = group.create_task(self._run_state_reader.wait_until_shutdown_requested())
            await asyncio.wait((restart, requested), return_when=asyncio.FIRST_COMPLETED)
            arm_shutdown_bound()
            for task in (rebuilds, restart, requested):
                task.cancel()
            # Every work, not only the searches: one asleep in its wait would hold the unwind
            # until the bound fires, and turn a clean stop into a forced one.
            for task in tuple(self._running):
                task.cancel()
        if not restart.cancelled():
            raise restart.result()

    def _add(
        self, supervised: SupervisedWork, *, over: SupervisedObject, group: asyncio.TaskGroup
    ) -> None:
        task = group.create_task(self._take_turns(supervised, over=over))
        self._running[task] = over
        task.add_done_callback(self._running.pop)

    async def _rebuild_each_decided(self, group: asyncio.TaskGroup) -> None:
        # Each in a task of its own, never in the turn that decided it, which the rebuild stops.
        async with asyncio.TaskGroup() as rebuilds:
            while True:
                supervised = await self._rebuilds_decided.get()
                rebuilds.create_task(self._rebuild(supervised, group=group))

    async def _rebuild(self, supervised: SupervisedObject, *, group: asyncio.TaskGroup) -> None:
        """Stops the works over the object, then has it rebuilt after 1, 2, then 4 min, a rebuild
        that raised counting in vain; the third leaves it unrepaired, holding no work."""
        await self._stop_works_over(supervised)
        while True:
            await self._monotonic_clock.sleep(supervised.wait_before_rebuild())
            if await self._rebuilt(supervised, group=group):
                return
            supervised.count_in_vain()
            if supervised.unrepaired:
                self._restart_if_a_function_is_lost()
                return

    def _restart_if_a_function_is_lost(self) -> None:
        """Ends the supervision once a function is wholly lost: every object serving it
        unrepaired, every one of its works failing, one that never turned not failing."""
        for function in CrawlerFunction:
            states = {
                supervised: supervised.states_of(function) for supervised in self._objects.values()
            }
            serving = [supervised for supervised, of_function in states.items() if of_function]
            works = {state for of_function in states.values() for state in of_function}
            lost = works == {HealthState.FAILING}
            if lost and all(supervised.unrepaired for supervised in serving):
                restart = CrawlerRestartError(function, rebuilds=REBUILDS_IN_VAIN_AT_MOST)
                self._restarts_decided.put_nowait(restart)
                return

    async def _stop_works_over(self, supervised: SupervisedObject) -> None:
        stopping = [task for task, over in self._running.items() if over is supervised]
        for task in stopping:
            task.cancel()
        for task in stopping:  # awaited, so no turn runs on the old object once it is rebuilt
            await asyncio.wait((task,))

    async def _rebuilt(self, supervised: SupervisedObject, *, group: asyncio.TaskGroup) -> bool:
        """Has the object rebuilt and runs the works over the new one; whether it was."""
        builder = supervised.builder
        try:
            works = await supervised.rebuild()
        except ExpectedError as error:  # an outage met by the close or the build: no bug
            self._logger.warning("rebuild of %s: %s", builder, error)
            return False
        except Exception as error:  # the boundary of a rebuild, by design
            self._logger.exception("bug in the rebuild of %s", builder, error=error)
            return False
        self._logger.info("%s rebuilt", builder)
        for work in works:
            self._add(work, over=supervised, group=group)
        return True

    async def _take_turns(self, supervised: SupervisedWork, *, over: SupervisedObject) -> None:
        met_a_bug = False
        while True:
            await self._wait(supervised.work, after_a_bug=met_a_bug)
            # The supervision sees a shutdown a few loop turns after the works: no turn starts then.
            if self._run_state_reader.is_shutdown_requested():
                return
            met_a_bug = await self._take_turn(supervised)
            if over.record_turn(supervised, met_a_bug=met_a_bug):
                self._rebuilds_decided.put_nowait(over)
            if over.unrepaired:
                self._restart_if_a_function_is_lost()

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
