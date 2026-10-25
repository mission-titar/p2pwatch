"""The promise of the ``RunStateReader`` and ``RunStateWriter`` pair.

A change is read after one ``asyncio.sleep(0)``: the port lets it follow the call, on the loop's
next tick.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Protocol

import pytest


class RunStateStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def set_paused(self, paused: bool) -> None: ...

    def set_shutdown_requested(self) -> None: ...

    def is_paused(self) -> bool: ...

    def is_shutdown_requested(self) -> bool: ...

    async def wait_until_resumed(self) -> None: ...

    async def wait_until_shutdown_requested(self) -> None: ...


class RunStateStoreContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def run_state_store(self) -> RunStateStore:
        """A run state no call has changed yet."""

    async def test_the_crawler_starts_resumed_without_a_shutdown_request(
        self, run_state_store: RunStateStore
    ) -> None:
        assert run_state_store.is_paused() is False
        assert run_state_store.is_shutdown_requested() is False

    async def test_a_pause_idles_the_crawler_and_requests_no_shutdown(
        self, run_state_store: RunStateStore
    ) -> None:
        run_state_store.set_paused(True)
        await asyncio.sleep(0)
        assert run_state_store.is_paused() is True
        assert run_state_store.is_shutdown_requested() is False

    async def test_unpausing_resumes_the_crawler(self, run_state_store: RunStateStore) -> None:
        run_state_store.set_paused(True)
        run_state_store.set_paused(False)
        await asyncio.sleep(0)
        assert run_state_store.is_paused() is False

    async def test_a_shutdown_request_leaves_the_crawler_resumed(
        self, run_state_store: RunStateStore
    ) -> None:
        run_state_store.set_shutdown_requested()
        await asyncio.sleep(0)
        assert run_state_store.is_shutdown_requested() is True
        assert run_state_store.is_paused() is False

    async def test_a_change_from_another_thread_is_read_from_another_thread(
        self, run_state_store: RunStateStore
    ) -> None:
        await asyncio.to_thread(run_state_store.set_paused, True)
        await asyncio.to_thread(run_state_store.set_shutdown_requested)
        await asyncio.sleep(0)
        assert await asyncio.to_thread(run_state_store.is_paused) is True
        assert await asyncio.to_thread(run_state_store.is_shutdown_requested) is True

    async def test_waiting_until_resumed_returns_at_once_when_resumed(
        self, run_state_store: RunStateStore
    ) -> None:
        waiting = asyncio.create_task(run_state_store.wait_until_resumed())
        await asyncio.sleep(0)
        assert waiting.done()

    async def test_waiting_until_resumed_returns_once_the_crawler_resumes(
        self, run_state_store: RunStateStore
    ) -> None:
        run_state_store.set_paused(True)
        await asyncio.sleep(0)
        waiting = asyncio.create_task(run_state_store.wait_until_resumed())
        await asyncio.sleep(0)
        assert not waiting.done()
        run_state_store.set_paused(False)
        await asyncio.wait_for(waiting, 1.0)

    async def test_waiting_until_shutdown_requested_returns_at_once_when_requested(
        self, run_state_store: RunStateStore
    ) -> None:
        run_state_store.set_shutdown_requested()
        await asyncio.sleep(0)
        waiting = asyncio.create_task(run_state_store.wait_until_shutdown_requested())
        await asyncio.sleep(0)
        assert waiting.done()

    async def test_waiting_until_shutdown_requested_returns_once_it_is_requested(
        self, run_state_store: RunStateStore
    ) -> None:
        waiting = asyncio.create_task(run_state_store.wait_until_shutdown_requested())
        await asyncio.sleep(0)
        assert not waiting.done()
        run_state_store.set_shutdown_requested()
        await asyncio.wait_for(waiting, 1.0)
