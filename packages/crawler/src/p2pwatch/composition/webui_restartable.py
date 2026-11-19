"""The webui as the node builds it, at its start and at each rebuild: the thread uvicorn serves it
on, built anew with the watch over that thread."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.ports.driven.restartable_builder import RestartableBuilder
from p2pwatch.application.steps.webui_thread_watch import WebuiThreadWatch
from p2pwatch.application.steps.work import SupervisedWork
from p2pwatch.composition.work_time_limits import TIME_LIMIT_MARGIN
from p2pwatch.domain.health.external_dependency import ExternalDependency


class WebuiThreadBuilder(Protocol):
    def __call__(self) -> UvicornServerThread: ...


# Every work over ``thread``, such as ``webui_thread_watch_over``.
class WorksOverWebuiThread(Protocol):
    def __call__(self, thread: UvicornServerThread, /) -> Sequence[SupervisedWork]: ...


def webui_thread_watch_over(
    thread: UvicornServerThread, *, dependency: ExternalDependency, monotonic_clock: MonotonicClock
) -> Sequence[SupervisedWork]:
    """The watch over ``thread``, its turns recorded on the webui's ``dependency``."""
    watch = WebuiThreadWatch(thread_alive=thread.is_alive, monotonic_clock=monotonic_clock)
    # Its turn awaits nothing: the margin alone.
    return [SupervisedWork(work=watch, time_limit=TIME_LIMIT_MARGIN, dependencies=(dependency,))]


class WebuiRestartable(Restartable[SupervisedWork]):
    """The webui serving on its thread, and the watch over that thread."""

    def __init__(self, thread: UvicornServerThread, *, works: Sequence[SupervisedWork]) -> None:
        self.thread = thread
        self._works = tuple(works)

    def works(self) -> Sequence[SupervisedWork]:
        return self._works

    async def close(self) -> None:
        """Stops its thread."""
        await self.thread.stop()


class WebuiRestartableBuilder(RestartableBuilder[SupervisedWork]):
    """Serves the webui on a thread built anew, a new app and new read connections, with the watch
    over that thread."""

    def __init__(
        self, *, build_thread: WebuiThreadBuilder, works_over: WorksOverWebuiThread
    ) -> None:
        self._build_thread = build_thread
        self._works_over = works_over

    def __str__(self) -> str:
        return "webui"

    async def build(self) -> WebuiRestartable:
        """A port held elsewhere leaves its thread ended, which its watch finds."""
        thread = self._build_thread()
        try:
            await thread.start()
        except BaseException:  # cut while it binds: the thread would serve on, held by nothing
            await thread.stop()
            raise
        return WebuiRestartable(thread, works=self._works_over(thread))
