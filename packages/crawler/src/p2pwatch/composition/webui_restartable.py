"""The webui as the node rebuilds it: the thread uvicorn serves it on, built anew with the watch
over that thread."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.restartable import Restartable
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
    """The webui's thread serving now, rebuilt with the watch over it: the node's shutdown stops
    the one it holds then."""

    def __init__(
        self,
        thread: UvicornServerThread,
        *,
        build_thread: WebuiThreadBuilder,
        works_over: WorksOverWebuiThread,
    ) -> None:
        self._thread = thread
        self._build_thread = build_thread
        self._works_over = works_over

    def __str__(self) -> str:
        return "webui"

    async def rebuild(self) -> Sequence[SupervisedWork]:
        """Stops the old thread, serves the webui on a thread built anew and returns the works
        over it; a port held elsewhere leaves the new thread ended, which its watch finds."""
        await self._thread.stop()
        # Held before its start: cut while it binds, the thread runs and the shutdown stops it.
        self._thread = self._build_thread()
        await self._thread.start()
        return self._works_over(self._thread)

    async def close(self) -> None:
        """Stops the thread it holds now."""
        await self._thread.stop()
