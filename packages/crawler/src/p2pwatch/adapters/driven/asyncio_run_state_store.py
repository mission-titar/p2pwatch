"""``AsyncioRunStateStore``: the run state on the crawler loop's events, changed from any thread.

The webui handlers run on the webui thread + loop; the crawler owns its ``asyncio.Event``s on its
MAIN loop. The load-bearing primitive is ``loop.call_soon_threadsafe``:
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

    The two events are the crawler's own (``CrawlerComposition``): ``resumed`` is the pause gate
    (set = running, clear = paused), and ``shutdown`` is the graceful-shutdown signal.
    """

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        resumed: asyncio.Event,
        shutdown: asyncio.Event,
    ) -> None:
        self._loop = loop
        self._resumed = resumed
        self._shutdown = shutdown

    def pause(self) -> None:
        self._loop.call_soon_threadsafe(self._resumed.clear)

    def resume(self) -> None:
        self._loop.call_soon_threadsafe(self._resumed.set)

    def shut_down(self) -> None:
        self._loop.call_soon_threadsafe(self._shutdown.set)

    def is_paused(self) -> bool:
        """A read, safe from another thread: ``is_set`` only returns a flag."""
        return not self._resumed.is_set()
