import asyncio

from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter


class FakeRunStateStore(RunStateWriter, RunStateReader):
    """Applies each change at once, where the real store hands it to the crawler's loop."""

    def __init__(self, *, paused: bool = False) -> None:
        self._resumed = asyncio.Event()
        self._shutdown_requested = asyncio.Event()
        self.set_paused(paused)

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._resumed.clear()
        else:
            self._resumed.set()

    def set_shutdown_requested(self) -> None:
        self._shutdown_requested.set()

    def is_paused(self) -> bool:
        return not self._resumed.is_set()

    def is_shutdown_requested(self) -> bool:
        return self._shutdown_requested.is_set()

    async def wait_until_resumed(self) -> None:
        await self._resumed.wait()

    async def wait_until_shutdown_requested(self) -> None:
        await self._shutdown_requested.wait()
