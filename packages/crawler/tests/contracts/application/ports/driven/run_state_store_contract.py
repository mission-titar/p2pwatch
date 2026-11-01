"""The promise of the ``RunStateReader`` and ``RunStateWriter`` pair.

A change is read after one ``asyncio.sleep(0)``: the port lets it follow the call, on the loop's
next tick.
"""

import asyncio
from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.run_state_reader import RunStateReader
from p2pwatch.application.ports.driven.run_state_writer import RunStateWriter


class RunStateStoreContract(ABC):
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    @abstractmethod
    def writer(self) -> RunStateWriter:
        """The writer of a run state no call has changed yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> RunStateReader:
        """The reader of the writer's run state."""

    async def test_the_crawler_starts_resumed_without_a_shutdown_request(
        self, reader: RunStateReader
    ) -> None:
        assert reader.is_paused() is False
        assert reader.is_shutdown_requested() is False

    async def test_a_pause_idles_the_crawler_and_requests_no_shutdown(
        self, *, writer: RunStateWriter, reader: RunStateReader
    ) -> None:
        writer.set_paused(True)
        await asyncio.sleep(0)  # noqa: TID251
        assert reader.is_paused() is True
        assert reader.is_shutdown_requested() is False

    async def test_unpausing_resumes_the_crawler(
        self, *, writer: RunStateWriter, reader: RunStateReader
    ) -> None:
        writer.set_paused(True)
        writer.set_paused(False)
        await asyncio.sleep(0)  # noqa: TID251
        assert reader.is_paused() is False

    async def test_a_shutdown_request_leaves_the_crawler_resumed(
        self, *, writer: RunStateWriter, reader: RunStateReader
    ) -> None:
        writer.set_shutdown_requested()
        await asyncio.sleep(0)  # noqa: TID251
        assert reader.is_shutdown_requested() is True
        assert reader.is_paused() is False

    async def test_a_change_from_another_thread_is_read_from_another_thread(
        self, *, writer: RunStateWriter, reader: RunStateReader
    ) -> None:
        await asyncio.to_thread(writer.set_paused, True)
        await asyncio.to_thread(writer.set_shutdown_requested)
        await asyncio.sleep(0)  # noqa: TID251
        assert await asyncio.to_thread(reader.is_paused) is True
        assert await asyncio.to_thread(reader.is_shutdown_requested) is True

    async def test_waiting_until_resumed_returns_at_once_when_resumed(
        self, reader: RunStateReader
    ) -> None:
        waiting = asyncio.create_task(reader.wait_until_resumed())
        await asyncio.sleep(0)  # noqa: TID251
        assert waiting.done()

    async def test_waiting_until_resumed_returns_once_the_crawler_resumes(
        self, *, writer: RunStateWriter, reader: RunStateReader
    ) -> None:
        writer.set_paused(True)
        await asyncio.sleep(0)  # noqa: TID251
        waiting = asyncio.create_task(reader.wait_until_resumed())
        await asyncio.sleep(0)  # noqa: TID251
        assert not waiting.done()
        writer.set_paused(False)
        await asyncio.wait_for(waiting, 1.0)

    async def test_waiting_until_shutdown_requested_returns_at_once_when_requested(
        self, *, writer: RunStateWriter, reader: RunStateReader
    ) -> None:
        writer.set_shutdown_requested()
        await asyncio.sleep(0)  # noqa: TID251
        waiting = asyncio.create_task(reader.wait_until_shutdown_requested())
        await asyncio.sleep(0)  # noqa: TID251
        assert waiting.done()

    async def test_waiting_until_shutdown_requested_returns_once_it_is_requested(
        self, *, writer: RunStateWriter, reader: RunStateReader
    ) -> None:
        waiting = asyncio.create_task(reader.wait_until_shutdown_requested())
        await asyncio.sleep(0)  # noqa: TID251
        assert not waiting.done()
        writer.set_shutdown_requested()
        await asyncio.wait_for(waiting, 1.0)
