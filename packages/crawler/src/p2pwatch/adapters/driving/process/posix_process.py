"""``PosixProcess``: the crawler's process, its two signals and the last close of what it holds."""

import asyncio
import signal
import sys
from contextlib import AsyncExitStack, suppress

from p2pwatch.application.ports.driving.shutdown_requester import ShutdownRequester

_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def _print_progress(message: str) -> None:
    """Human shutdown line on stderr: the stop's progress is shown outside logging."""
    print(message, file=sys.stderr, flush=True)


class PosixProcess:
    """A first SIGINT or SIGTERM requests the shutdown, a second exits at once.

    Entered, it gives the stack of the resources it holds, and closes them on exit.
    """

    def __init__(self, shutdown_requester: ShutdownRequester) -> None:
        self._shutdown_requester = shutdown_requester
        self._resources = AsyncExitStack()
        self._signal_count = 0

    async def __aenter__(self) -> AsyncExitStack:
        # A loop handler, not ``KeyboardInterrupt``, which would preempt a sync function mid-write.
        loop = asyncio.get_running_loop()
        for signal_number in _SIGNALS:
            loop.add_signal_handler(signal_number, self._on_signal)
        return self._resources

    async def __aexit__(self, *_exc_info: object) -> None:
        # Best effort after a fired deadline or a failed setup: its failures never mask the first.
        with suppress(BaseException):
            await self._resources.aclose()
        loop = asyncio.get_running_loop()
        for signal_number in _SIGNALS:
            loop.remove_signal_handler(signal_number)

    def _on_signal(self) -> None:
        self._signal_count += 1
        if self._signal_count == 1:
            _print_progress(
                "Shutdown requested: finishing in-flight searches, clean close… "
                "(Ctrl-C again to force)"
            )
            self._shutdown_requester.request_shutdown()
        else:
            _print_progress("Forced shutdown.")
            raise SystemExit(1)
