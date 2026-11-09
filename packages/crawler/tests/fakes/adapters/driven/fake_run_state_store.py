import asyncio

from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter


class FakeRunStateStore(RunStateWriter, RunStateReader):
    """Applies each change at once, on the caller's thread."""

    def __init__(self) -> None:
        self._shutdown_requested = asyncio.Event()

    def set_shutdown_requested(self) -> None:
        self._shutdown_requested.set()

    def is_shutdown_requested(self) -> bool:
        return self._shutdown_requested.is_set()

    async def wait_until_shutdown_requested(self) -> None:
        await self._shutdown_requested.wait()
