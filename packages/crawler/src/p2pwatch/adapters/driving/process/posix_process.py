"""``PosixProcess``: the crawler's process and its two signals."""

import asyncio
import os
import signal
from typing import Self

from p2pwatch.application.ports.driving.shutdown_requester import ShutdownRequester

_SIGNALS = (signal.SIGINT, signal.SIGTERM)


def _write_progress(message: str) -> None:
    """Human shutdown line on stderr, outside logging: ``os.write`` takes no lock, so a plain
    handler can write it at any bytecode, mid-``print`` included."""
    os.write(2, f"{message}\n".encode())


class PosixProcess:
    """A first SIGINT or SIGTERM requests the shutdown, a second exits: while the start's
    synchronous steps hold the event loop, a plain handler sets the flag they read and defers the
    exit to the loop's first turn; once the loop runs, the loop's own handler, at once."""

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
            self._install_loop_handlers()
        # The loop's removal gives each signal its default handler back.
        loop = asyncio.get_running_loop()
        for signal_number in _SIGNALS:
            loop.remove_signal_handler(signal_number)
        self._exit_if_forced()

    def is_signalled(self) -> bool:
        """Whether a signal requested the shutdown, set at once while the start holds the loop."""
        return self._signal_count > 0

    def _hand_over_to_the_loop(self) -> None:
        self._install_loop_handlers()
        self._exit_if_forced()

    def _install_loop_handlers(self) -> None:
        # A loop handler, not a plain one, whose ``SystemExit`` would preempt a sync function
        # mid-write: each replaces the plain handler at once, so no signal meets the default.
        loop = asyncio.get_running_loop()
        for signal_number in _SIGNALS:
            loop.add_signal_handler(signal_number, self._on_signal)
        self._on_the_loop = True

    def _exit_if_forced(self) -> None:
        if self._signal_count > 1:
            raise SystemExit(1)

    def _on_signal_holding_the_loop(self, *_signal_and_frame: object) -> None:
        # Raises nothing: sqlite3 would swallow an exit raised inside a progress handler.
        self._count_signal()

    def _on_signal(self) -> None:
        self._count_signal()
        self._exit_if_forced()

    def _count_signal(self) -> None:
        self._signal_count += 1
        if self._signal_count == 1:
            _write_progress(
                "Shutdown requested: finishing in-flight searches, clean close… "
                "(Ctrl-C again to force)"
            )
            # Callable from a plain handler: the run state schedules its change on the loop.
            self._shutdown_requester.request_shutdown()
        else:
            _write_progress("Forced shutdown.")
