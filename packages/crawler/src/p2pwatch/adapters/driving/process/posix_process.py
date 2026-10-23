"""``PosixProcess``: the crawler's process and its two signals."""

import asyncio
import signal
import sys

from p2pwatch.application.ports.driving.shutdown_requester import ShutdownRequester

_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def _print_progress(message: str) -> None:
    """Human shutdown line on stderr: the stop's progress is shown outside logging."""
    print(message, file=sys.stderr, flush=True)


class PosixProcess:
    """A first SIGINT or SIGTERM requests the shutdown, a second exits at once."""

    def __init__(self, shutdown_requester: ShutdownRequester) -> None:
        self._shutdown_requester = shutdown_requester
        self._signal_count = 0

    async def __aenter__(self) -> None:
        # A loop handler, not ``KeyboardInterrupt``, which would preempt a sync function mid-write.
        loop = asyncio.get_running_loop()
        for signal_number in _SIGNALS:
            loop.add_signal_handler(signal_number, self._on_signal)

    async def __aexit__(self, *_exc_info: object) -> None:
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
