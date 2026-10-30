import asyncio
import logging
import socket
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from tests.fakes.adapters.driven.fake_serving_resource import FakeServingResource

_LOGGER = "p2pwatch.adapters.driving.webui.uvicorn_server_thread"


async def _ok(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _webui_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == "webui"]


@pytest.mark.asyncio
async def test_start_serves_the_app_on_the_port_bound_and_stop_ends_the_thread(
    caplog: pytest.LogCaptureFixture,
) -> None:
    server_thread = UvicornServerThread(
        Starlette(routes=[Route("/", _ok)]),
        address=("127.0.0.1", 0),
        start_timeout_seconds=5.0,
        join_timeout_seconds=5.0,
        serving_resources=(),
    )
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await server_thread.start()
    host, port = server_thread.bound_address
    try:
        async with httpx.AsyncClient() as http:
            response = await http.get(f"http://{host}:{port}/")
    finally:
        await server_thread.stop()
    assert (host, response.text) == ("127.0.0.1", "ok")
    assert port != 0
    assert f"webui serving on 127.0.0.1:{port} (own thread)" in caplog.messages
    assert _webui_threads() == []


@pytest.mark.asyncio
async def test_the_access_log_leaves_out_the_metrics_scrapes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    server_thread = UvicornServerThread(
        Starlette(routes=[Route("/", _ok), Route("/metrics", _ok)]),
        address=("127.0.0.1", 0),
        start_timeout_seconds=5.0,
        join_timeout_seconds=5.0,
        serving_resources=(),
    )
    # uvicorn's access logger does not propagate: caplog reads it through a handler of its own.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(caplog.handler)
    try:
        await server_thread.start()
        host, port = server_thread.bound_address
        async with httpx.AsyncClient() as http:
            await http.get(f"http://{host}:{port}/metrics")
            await http.get(f"http://{host}:{port}/")
        await server_thread.stop()
    finally:
        access_logger.removeHandler(caplog.handler)
    access_lines = [
        record.getMessage().split(" - ")[1]
        for record in caplog.records
        if record.name == "uvicorn.access"
    ]
    assert access_lines == ['"GET / HTTP/1.1" 200']


@pytest.mark.asyncio
async def test_a_port_already_bound_degrades_the_webui_without_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        server_thread = UvicornServerThread(
            Starlette(),
            address=holder.getsockname(),
            start_timeout_seconds=5.0,
            join_timeout_seconds=5.0,
            serving_resources=(),
        )
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await server_thread.start()
        await server_thread.stop()
    assert caplog.messages == ["webui degraded: the crawler carries on without HTTP"]
    assert "address already in use" in caplog.text
    assert _webui_threads() == []


@pytest.mark.asyncio
async def test_a_server_that_does_not_start_in_time_degrades_the_webui(
    caplog: pytest.LogCaptureFixture,
) -> None:
    released = threading.Event()

    @asynccontextmanager
    async def held_startup(app: Starlette) -> AsyncIterator[None]:
        await asyncio.to_thread(released.wait)
        yield

    server_thread = UvicornServerThread(
        Starlette(lifespan=held_startup),
        address=("127.0.0.1", 0),
        start_timeout_seconds=0.05,
        join_timeout_seconds=5.0,
        serving_resources=(),
    )
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await server_thread.start()
    released.set()
    await server_thread.stop()
    assert caplog.messages == ["webui degraded: uvicorn did not start within 0.05 s"]
    assert _webui_threads() == []


@pytest.mark.asyncio
async def test_stop_gives_up_on_a_server_that_does_not_end_within_its_join_timeout() -> None:
    released = threading.Event()

    @asynccontextmanager
    async def held_shutdown(app: Starlette) -> AsyncIterator[None]:
        yield
        await asyncio.to_thread(released.wait)

    server_thread = UvicornServerThread(
        Starlette(lifespan=held_shutdown),
        address=("127.0.0.1", 0),
        start_timeout_seconds=5.0,
        join_timeout_seconds=0.05,
        serving_resources=(),
    )
    await server_thread.start()
    await server_thread.stop()
    still_serving = _webui_threads()
    released.set()
    for thread in still_serving:
        thread.join(timeout=5.0)
    assert len(still_serving) == 1


@pytest.mark.asyncio
async def test_a_failing_lifespan_degrades_the_webui_without_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    @asynccontextmanager
    async def failing_startup(app: Starlette) -> AsyncIterator[None]:
        raise RuntimeError("startup refused")
        yield

    server_thread = UvicornServerThread(
        Starlette(lifespan=failing_startup),
        address=("127.0.0.1", 0),
        start_timeout_seconds=5.0,
        join_timeout_seconds=5.0,
        serving_resources=(),
    )
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        await server_thread.start()
    await server_thread.stop()
    assert caplog.messages == ["webui degraded: the crawler carries on without HTTP"]
    assert _webui_threads() == []


@pytest.mark.asyncio
async def test_the_serving_resources_are_held_by_the_webui_thread_while_it_serves() -> None:
    resource = FakeServingResource()
    server_thread = UvicornServerThread(
        Starlette(),
        address=("127.0.0.1", 0),
        start_timeout_seconds=5.0,
        join_timeout_seconds=5.0,
        serving_resources=(resource,),
    )
    await server_thread.start()
    entered = list(resource.threads)
    await server_thread.stop()
    assert entered == [("enter", "webui")]
    assert resource.threads == [("enter", "webui"), ("exit", "webui")]


@pytest.mark.asyncio
async def test_the_serving_resources_are_left_when_serving_fails() -> None:
    resource = FakeServingResource()
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        server_thread = UvicornServerThread(
            Starlette(),
            address=holder.getsockname(),
            start_timeout_seconds=5.0,
            join_timeout_seconds=5.0,
            serving_resources=(resource,),
        )
        await server_thread.start()
        await server_thread.stop()
    assert resource.threads == [("enter", "webui"), ("exit", "webui")]
