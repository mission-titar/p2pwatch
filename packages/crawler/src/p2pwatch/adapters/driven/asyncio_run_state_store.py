"""``AsyncioRunStateStore``: the run state on the crawler loop's events, changed from any thread.

The webui handlers run on the webui thread + loop; the store's ``asyncio.Event``s belong to the
crawler's MAIN loop. The load-bearing primitive is ``loop.call_soon_threadsafe``:
``asyncio.Event.set()``/``.clear()`` are NOT safe to call directly from another thread (they may
need to wake waiters scheduled on the crawler loop, and the events are affine to that loop), so
every change is SCHEDULED to run ON the crawler loop thread. The call returns immediately; the
change happens on the next crawler loop tick.
"""

import asyncio

from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter


class AsyncioRunStateStore(RunStateWriter, RunStateReader):
    """Forwards each change onto the crawler loop via ``call_soon_threadsafe``.

    ``resumed`` is the pause gate (set = running, clear = paused), and ``shutdown_requested`` the
    graceful-shutdown signal. The crawler starts resumed.
    """

    def __init__(self, *, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._resumed = asyncio.Event()
        self._resumed.set()
        self._shutdown_requested = asyncio.Event()

    def set_paused(self, paused: bool) -> None:
        self._loop.call_soon_threadsafe(self._resumed.clear if paused else self._resumed.set)

    def set_shutdown_requested(self) -> None:
        self._loop.call_soon_threadsafe(self._shutdown_requested.set)

    def is_paused(self) -> bool:
        """A read, safe from another thread: ``is_set`` only returns a flag."""
        return not self._resumed.is_set()

    def is_shutdown_requested(self) -> bool:
        return self._shutdown_requested.is_set()

    async def wait_until_resumed(self) -> None:
        await self._resumed.wait()

    async def wait_until_shutdown_requested(self) -> None:
        await self._shutdown_requested.wait()
