"""Tests for ``AsyncioRunStateStore``, the run state the webui changes from its own thread."""

import asyncio

import pytest_asyncio

from p2pwatch.adapters.driven.asyncio_run_state_store import AsyncioRunStateStore
from tests.contracts.application.ports.driven.run_state_store_contract import (
    RunStateStoreContract,
)
from tests.fakes.adapters.driven.fake_recording_event_loop import FakeRecordingEventLoop


class TestAsyncioRunStateStore(RunStateStoreContract):
    @pytest_asyncio.fixture
    async def run_state_store(self) -> AsyncioRunStateStore:
        return AsyncioRunStateStore(loop=asyncio.get_running_loop())


def test_a_change_is_deferred_to_the_loop_thread_via_call_soon_threadsafe() -> None:
    """Nothing changes inline on the caller's thread: the change applies once the loop runs it."""
    loop = FakeRecordingEventLoop()
    run_state = AsyncioRunStateStore(
        loop=loop,  # type: ignore[arg-type]  # fake loop, only call_soon_threadsafe is used
    )
    run_state.set_shutdown_requested()
    assert len(loop.callbacks) == 1
    assert not run_state.is_shutdown_requested()
    loop.callbacks[0]()
    assert run_state.is_shutdown_requested()
