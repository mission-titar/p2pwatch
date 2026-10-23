"""Tests for ``AsyncioRunStateStore``, the run state the webui changes from its own thread.

The load-bearing property: every change is HANDED OFF to the crawler loop via
``loop.call_soon_threadsafe`` (never applied inline on the caller/webui thread). Two fake loops
model the two facets:

- ``FakeImmediateEventLoop`` runs the scheduled callback INLINE (models the crawler loop having
  already drained the callback), so we can assert what each method changes.
- ``FakeRecordingEventLoop`` RECORDS the scheduled callback WITHOUT running it, so we can assert the
  change is DEFERRED (nothing reads changed until the loop runs the callback).
"""

import asyncio

import pytest

from p2pwatch.adapters.driven.asyncio_run_state_store import AsyncioRunStateStore
from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter
from tests.fakes.adapters.driven.fake_immediate_event_loop import FakeImmediateEventLoop
from tests.fakes.adapters.driven.fake_recording_event_loop import FakeRecordingEventLoop


def _run_state_with(loop: object) -> tuple[RunStateWriter, RunStateReader]:
    """The run state seen through its two ports."""
    run_state = AsyncioRunStateStore(
        loop=loop,  # type: ignore[arg-type]  # fake loop, only call_soon_threadsafe is used
    )
    return run_state, run_state


def test_the_crawler_starts_resumed_and_without_a_shutdown_request() -> None:
    _writer, reader = _run_state_with(FakeRecordingEventLoop())
    assert not reader.is_paused()
    assert not reader.is_shutdown_requested()


def test_setting_paused_pauses_and_requests_no_shutdown() -> None:
    writer, reader = _run_state_with(FakeImmediateEventLoop())
    writer.set_paused(True)
    assert reader.is_paused()
    assert not reader.is_shutdown_requested()


def test_setting_unpaused_resumes() -> None:
    writer, reader = _run_state_with(FakeImmediateEventLoop())
    writer.set_paused(True)
    writer.set_paused(False)
    assert not reader.is_paused()


def test_setting_shutdown_requested_requests_it_and_leaves_the_pause() -> None:
    writer, reader = _run_state_with(FakeImmediateEventLoop())
    writer.set_shutdown_requested()
    assert reader.is_shutdown_requested()
    assert not reader.is_paused()


def test_a_change_is_deferred_to_the_loop_thread_via_call_soon_threadsafe() -> None:
    """The hand-off goes through ``call_soon_threadsafe``: nothing changes inline on the caller
    thread; the change is scheduled and only applies once the loop runs the callback."""
    loop = FakeRecordingEventLoop()
    writer, reader = _run_state_with(loop)
    writer.set_shutdown_requested()
    # Scheduled, but NOT yet applied (deferred to the crawler loop thread).
    assert len(loop.callbacks) == 1
    assert not reader.is_shutdown_requested()
    # Running the scheduled callback (as the loop thread would) applies the change.
    loop.callbacks[0]()
    assert reader.is_shutdown_requested()


@pytest.mark.asyncio
async def test_waiting_until_resumed_returns_once_the_crawler_loop_resumes() -> None:
    writer, reader = _run_state_with(asyncio.get_running_loop())
    writer.set_paused(True)
    waiting = asyncio.create_task(reader.wait_until_resumed())
    await asyncio.sleep(0)
    assert not waiting.done()
    writer.set_paused(False)
    await asyncio.wait_for(waiting, 1.0)


@pytest.mark.asyncio
async def test_waiting_until_shutdown_requested_returns_once_the_crawler_loop_has_it() -> None:
    writer, reader = _run_state_with(asyncio.get_running_loop())
    waiting = asyncio.create_task(reader.wait_until_shutdown_requested())
    await asyncio.sleep(0)
    assert not waiting.done()
    writer.set_shutdown_requested()
    await asyncio.wait_for(waiting, 1.0)
