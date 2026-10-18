"""Tests for ``LoopCrawlerControl`` (webui to crawler-loop control adapter, phase P6a).

The load-bearing property: every control mutation is HANDED OFF to the crawler loop via
``loop.call_soon_threadsafe`` (never applied inline on the caller/webui thread). Two fake loops
model the two facets:

- ``_ImmediateLoop`` runs the scheduled callback INLINE (models the crawler loop having already
  drained the callback), so we can assert which event each method mutates.
- ``_RecordingLoop`` RECORDS the scheduled callback WITHOUT running it, so we can assert the
  mutation is DEFERRED (the event is not touched until the loop runs the callback).
"""

import asyncio
from collections.abc import Callable

from p2pwatch.adapters.driven.crawler_control_loop import LoopCrawlerControl


class _ImmediateLoop:
    """Fake loop whose ``call_soon_threadsafe`` runs the callback INLINE."""

    def __init__(self) -> None:
        self.scheduled = 0

    def call_soon_threadsafe(self, callback: Callable[[], None]) -> None:
        self.scheduled += 1
        callback()


class _RecordingLoop:
    """Fake loop that RECORDS scheduled callbacks WITHOUT running them (deferral proof)."""

    def __init__(self) -> None:
        self.callbacks: list[Callable[[], None]] = []

    def call_soon_threadsafe(self, callback: Callable[[], None]) -> None:
        self.callbacks.append(callback)


def _control_with(loop: object) -> tuple[LoopCrawlerControl, asyncio.Event, asyncio.Event]:
    resumed = asyncio.Event()
    shutdown = asyncio.Event()
    control = LoopCrawlerControl(
        loop=loop,  # type: ignore[arg-type]  # fake loop, only call_soon_threadsafe is used
        resumed=resumed,
        shutdown=shutdown,
    )
    return control, resumed, shutdown


def test_pause_clears_the_resumed_event() -> None:
    control, resumed, shutdown = _control_with(_ImmediateLoop())
    resumed.set()  # running
    control.pause()
    assert not resumed.is_set()
    assert not shutdown.is_set()


def test_resume_sets_the_resumed_event() -> None:
    control, resumed, shutdown = _control_with(_ImmediateLoop())
    resumed.clear()  # paused
    control.resume()
    assert resumed.is_set()
    assert not shutdown.is_set()


def test_request_shutdown_sets_only_the_shutdown_event() -> None:
    control, resumed, shutdown = _control_with(_ImmediateLoop())
    control.request_shutdown()
    assert shutdown.is_set()
    assert not resumed.is_set()


def test_control_holds_no_db_connection_and_only_events_plus_loop() -> None:
    """Structural read-only guarantee (spec §4): the control's only effect is scheduling event
    mutations on the loop. It holds NO DB connection / cannot write: its slots, the only state
    it can hold, are exactly the loop + the two events."""
    loop = _ImmediateLoop()
    control, resumed, shutdown = _control_with(loop)
    assert LoopCrawlerControl.__slots__ == ("_loop", "_resumed", "_shutdown")
    held: tuple[object, ...] = (control._loop, control._resumed, control._shutdown)
    assert held == (loop, resumed, shutdown)


def test_mutation_is_deferred_to_the_loop_thread_via_call_soon_threadsafe() -> None:
    """The hand-off goes through ``call_soon_threadsafe``: the event is NOT mutated inline on the
    caller thread; it is scheduled and only mutates once the loop runs the callback."""
    loop = _RecordingLoop()
    control, _resumed, shutdown = _control_with(loop)
    control.request_shutdown()
    # Scheduled, but NOT yet applied (deferred to the crawler loop thread).
    assert len(loop.callbacks) == 1
    assert not shutdown.is_set()
    # Running the scheduled callback (as the loop thread would) applies the mutation.
    loop.callbacks[0]()
    assert shutdown.is_set()


def test_is_paused_reads_the_pause_gate() -> None:
    control, resumed, _ = _control_with(_RecordingLoop())
    assert control.is_paused()
    resumed.set()
    assert not control.is_paused()
