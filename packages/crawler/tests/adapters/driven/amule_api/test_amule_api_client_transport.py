"""``AmuleApiClient`` over loopback sockets: each transport failure is an unreachable daemon."""

import asyncio
import socket
import struct
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from typing import Protocol

import httpx
import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.domain.client_errors import ClientUnreachableError
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.fake_amule_api import PASSWORD


class ConnectionHandler(Protocol):
    async def __call__(
        self, *, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None: ...


def _client(
    port: int, *, timeout_seconds: float = 5.0, request_bound_seconds: float = 10.0
) -> AmuleApiClient:
    return AmuleApiClient(
        "127.0.0.1",
        port=port,
        password=PASSWORD,
        timeout_seconds=timeout_seconds,
        request_bound_seconds=request_bound_seconds,
        page_size=500,
        progress_poll_interval=timedelta(seconds=5),
        monotonic_clock=FakeTime().monotonic,
        transport_factory=httpx.AsyncHTTPTransport,
    )


@asynccontextmanager
async def _serving(handler: ConnectionHandler) -> AsyncIterator[int]:
    """A loopback server running ``handler`` on each connection; its port."""
    server = await asyncio.start_server(
        lambda reader, writer: handler(reader=reader, writer=writer), host="127.0.0.1", port=0
    )
    try:
        yield server.sockets[0].getsockname()[1]
    finally:
        server.close()
        await server.wait_closed()


async def _reset_after_the_request(
    *, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    await reader.readuntil(b"\r\n\r\n")
    # A zero linger makes the close send RST, as a crashed peer's kernel does.
    linger = struct.pack("ii", 1, 0)
    writer.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
    writer.transport.abort()


async def _close_after_the_request(
    *, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    await reader.readuntil(b"\r\n\r\n")
    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler",
    [_reset_after_the_request, _close_after_the_request],
    ids=["reset", "closed without an answer"],
)
async def test_a_connection_lost_before_its_answer_is_an_unreachable_daemon(
    handler: ConnectionHandler,
) -> None:
    async with _serving(handler) as port:
        client = _client(port)

        with pytest.raises(ClientUnreachableError, match="POST /auth/login"):
            await client.status()
        await client.close()


@pytest.mark.asyncio
async def test_an_answer_past_the_timeout_is_an_unreachable_daemon() -> None:
    released = asyncio.Event()

    async def answer_nothing(*, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await released.wait()
        writer.close()

    async with _serving(answer_nothing) as port:
        client = _client(port, timeout_seconds=0.1)
        try:
            with pytest.raises(ClientUnreachableError, match="POST /auth/login"):
                await client.status()
        finally:
            released.set()
        await client.close()


@pytest.mark.asyncio
async def test_an_answer_trickled_past_the_request_bound_is_an_unreachable_daemon() -> None:
    released = asyncio.Event()

    async def trickle(*, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 1000000\r\n\r\n")
        with suppress(ConnectionError):
            while not released.is_set():  # each byte within the phase timeout
                writer.write(b" ")
                await writer.drain()
                await asyncio.sleep(0.05)  # noqa: TID251
        writer.close()

    async with _serving(trickle) as port:
        client = _client(port, timeout_seconds=0.2, request_bound_seconds=0.5)
        try:
            async with asyncio.timeout(5):
                with pytest.raises(ClientUnreachableError, match="POST /auth/login"):
                    await client.status()
        finally:
            released.set()
        await client.close()


@pytest.mark.asyncio
async def test_a_refused_connection_is_an_unreachable_daemon() -> None:
    with socket.create_server(("127.0.0.1", 0)) as bound:
        port = bound.getsockname()[1]
    client = _client(port)

    with pytest.raises(ClientUnreachableError, match="POST /auth/login"):
        await client.status()
    await client.close()
