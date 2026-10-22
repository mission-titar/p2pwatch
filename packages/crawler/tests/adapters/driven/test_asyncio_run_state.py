"""Tests for ``AsyncioRunState``, the run state the webui changes from its own thread.

The load-bearing property: every change is HANDED OFF to the crawler loop via
``loop.call_soon_threadsafe`` (never applied inline on the caller/webui thread). Two fake loops
model the two facets:

- ``ImmediateLoop`` runs the scheduled callback INLINE (models the crawler loop having already
  drained the callback), so we can assert which event each method mutates.
- ``RecordingLoop`` RECORDS the scheduled callback WITHOUT running it, so we can assert the
  mutation is DEFERRED (the event is not touched until the loop runs the callback).
"""

import asyncio

from p2pwatch.adapters.driven.asyncio_run_state import AsyncioRunState
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter
from tests.fakes.adapters.driven.immediate_loop import ImmediateLoop
from tests.fakes.adapters.driven.recording_loop import RecordingLoop


def _run_state_with(
    loop: object,
) -> tuple[RunStateWriter, RunStateReader, asyncio.Event, asyncio.Event]:
    """The run state seen through its two ports, and its two events."""
    resumed = asyncio.Event()
    shutdown = asyncio.Event()
    run_state = AsyncioRunState(
        loop=loop,  # type: ignore[arg-type]  # fake loop, only call_soon_threadsafe is used
        resumed=resumed,
        shutdown=shutdown,
    )
    return run_state, run_state, resumed, shutdown


def test_pause_clears_the_resumed_event() -> None:
    writer, _reader, resumed, shutdown = _run_state_with(ImmediateLoop())
    resumed.set()  # running
    writer.pause()
    assert not resumed.is_set()
    assert not shutdown.is_set()


def test_resume_sets_the_resumed_event() -> None:
    writer, _reader, resumed, shutdown = _run_state_with(ImmediateLoop())
    resumed.clear()  # paused
    writer.resume()
    assert resumed.is_set()
    assert not shutdown.is_set()


def test_shut_down_sets_only_the_shutdown_event() -> None:
    writer, _reader, resumed, shutdown = _run_state_with(ImmediateLoop())
    writer.shut_down()
    assert shutdown.is_set()
    assert not resumed.is_set()


def test_mutation_is_deferred_to_the_loop_thread_via_call_soon_threadsafe() -> None:
    """The hand-off goes through ``call_soon_threadsafe``: the event is NOT mutated inline on the
    caller thread; it is scheduled and only mutates once the loop runs the callback."""
    loop = RecordingLoop()
    writer, _reader, _resumed, shutdown = _run_state_with(loop)
    writer.shut_down()
    # Scheduled, but NOT yet applied (deferred to the crawler loop thread).
    assert len(loop.callbacks) == 1
    assert not shutdown.is_set()
    # Running the scheduled callback (as the loop thread would) applies the mutation.
    loop.callbacks[0]()
    assert shutdown.is_set()


def test_is_paused_reads_the_pause_gate() -> None:
    _writer, reader, resumed, _shutdown = _run_state_with(RecordingLoop())
    assert reader.is_paused()
    resumed.set()
    assert not reader.is_paused()
