"""``PosixProcess``: the crawler's process and its two signals."""

import asyncio
import signal
import sys
from typing import Self

from p2pwatch.application.ports.driving.shutdown_requester import ShutdownRequester

_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def _print_progress(message: str) -> None:
    """Human shutdown line on stderr: the stop's progress is shown outside logging."""
    print(message, file=sys.stderr, flush=True)


class PosixProcess:
    """A first SIGINT or SIGTERM requests the shutdown, a second exits at once: while the start's
    synchronous steps hold the event loop, a plain handler sets the flag they read; once the loop
    runs, the loop's own handler."""

    def __init__(self, shutdown_requester: ShutdownRequester) -> None:
        self._shutdown_requester = shutdown_requester
        self._signal_count = 0
        self._on_the_loop = False

    async def __aenter__(self) -> Self:
        for signal_number in _SIGNALS:
            signal.signal(signal_number, self._on_signal_holding_the_loop)
        self._handover = asyncio.get_running_loop().call_soon(self._hand_over_to_the_loop)
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        self._handover.cancel()
        if not self._on_the_loop:
            self._hand_over_to_the_loop()
        # The loop's removal gives each signal its default handler back.
        loop = asyncio.get_running_loop()
        for signal_number in _SIGNALS:
            loop.remove_signal_handler(signal_number)

    def is_signalled(self) -> bool:
        """Whether a signal requested the shutdown, set at once while the start holds the loop."""
        return self._signal_count > 0

    def _hand_over_to_the_loop(self) -> None:
        # A loop handler, not a plain one, whose ``SystemExit`` would preempt a sync function
        # mid-write: each replaces the plain handler at once, so no signal meets the default.
        loop = asyncio.get_running_loop()
        for signal_number in _SIGNALS:
            loop.add_signal_handler(signal_number, self._on_signal)
        self._on_the_loop = True

    def _on_signal_holding_the_loop(self, *_signal_and_frame: object) -> None:
        self._on_signal()

    def _on_signal(self) -> None:
        self._signal_count += 1
        if self._signal_count == 1:
            _print_progress(
                "Shutdown requested: finishing in-flight searches, clean close… "
                "(Ctrl-C again to force)"
            )
            # Callable from a plain handler: the run state schedules its change on the loop.
            self._shutdown_requester.request_shutdown()
        else:
            _print_progress("Forced shutdown.")
            raise SystemExit(1)
