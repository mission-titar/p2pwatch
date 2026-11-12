"""The webui thread's owner: the thread uvicorn serves the webui on, built anew by a restart with
the webui it serves (spec v5 lot 4, D5)."""

from collections.abc import Sequence
from typing import Protocol

from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.application.steps.supervisor import SupervisedWork
from p2pwatch.composition.amule_client_owner import WorkAdder


class ThreadBuilder(Protocol):
    def __call__(self) -> UvicornServerThread: ...


# Every work over ``thread``, built anew.
class ThreadWorks(Protocol):
    def __call__(self, thread: UvicornServerThread, /) -> Sequence[SupervisedWork]: ...


class WebuiThreadOwner(StateOwner):
    """Holds the thread serving the webui now, which the resource stack stops at the shutdown."""

    def __init__(
        self,
        thread: UvicornServerThread,
        *,
        build_thread: ThreadBuilder,
        build_works: ThreadWorks,
        add_work: WorkAdder,
    ) -> None:
        self._thread = thread
        self._build_thread = build_thread
        self._build_works = build_works
        self._add_work = add_work

    def __str__(self) -> str:
        return "webui thread"

    async def restart(self) -> None:
        """Stops the old thread, then serves the webui on a thread built anew, and adds the works
        over it."""
        await self._thread.stop()
        # Held before its start, so the shutdown stops it even when the start is cut.
        self._thread = self._build_thread()
        await self._thread.start()
        for supervised in self._build_works(self._thread):
            self._add_work(supervised)

    async def close(self) -> None:
        await self._thread.stop()
