"""The webui as the node builds it, at its start and at each rebuild: served on a thread built
anew, with the watch over that thread; its close stops the thread."""

import asyncio
import socket
import threading
from collections.abc import AsyncIterator, Sequence
from datetime import timedelta

import httpx
import pytest
import pytest_asyncio
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.webui_thread_watch import WebuiThreadEndedError
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.webui_restartable import (
    WebuiRestartable,
    WebuiRestartableBuilder,
    webui_thread_watch_over,
)
from tests.contracts.application.ports.driven.restartable_builder_contract import (
    RestartableBuilderContract,
)
from tests.fakes.adapters.driven.fake_time import FakeTime


async def _ok(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


class _Over(Work):
    """A work over one webui thread, never run."""

    def __init__(self, thread: UvicornServerThread) -> None:
        self.thread = thread

    def __str__(self) -> str:
        return "webui"

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


def _works_over(thread: UvicornServerThread, /) -> Sequence[SupervisedWork]:
    return [SupervisedWork(work=_Over(thread), time_limit=timedelta(minutes=5))]


class _Threads:
    """Builds the webui's threads on ``address``, keeping each, as the composition builds them."""

    def __init__(self, address: tuple[str, int] = ("127.0.0.1", 0)) -> None:
        self.address = address
        self.built: list[UvicornServerThread] = []

    def build(self) -> UvicornServerThread:
        self.built.append(
            UvicornServerThread(
                Starlette(routes=[Route("/", _ok)]),
                address=self.address,
                start_timeout_seconds=5.0,
                join_timeout_seconds=5.0,
                serving_resources=(),
            )
        )
        return self.built[-1]


@pytest_asyncio.fixture
async def threads() -> AsyncIterator[_Threads]:
    """The webui's threads a test builds, each stopped at its end."""
    threads = _Threads()
    yield threads
    for thread in threads.built:
        await thread.stop()


@pytest.fixture
def webui(threads: _Threads) -> WebuiRestartableBuilder:
    """The webui's builder, its threads ``threads``, its works ``_works_over``."""
    return WebuiRestartableBuilder(build_thread=threads.build, works_over=_works_over)


def _webui_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == "webui"]


async def _served(thread: UvicornServerThread) -> str:
    host, port = thread.bound_address
    async with httpx.AsyncClient() as http:
        return (await http.get(f"http://{host}:{port}/")).text


class TestWebuiRestartableBuilder(RestartableBuilderContract):
    @pytest.fixture
    def restartable_builder(self, webui: WebuiRestartableBuilder) -> WebuiRestartableBuilder:
        return webui

    def state_of(self, restartable: Restartable[object]) -> object:
        assert isinstance(restartable, WebuiRestartable)
        return restartable.thread

    def state_reached(self, restartable: Restartable[object]) -> object:
        [supervised] = restartable.works()
        assert isinstance(supervised, SupervisedWork)
        assert isinstance(supervised.work, _Over)
        return supervised.work.thread


def test_it_names_its_webuis_as_the_webui_s_part_is() -> None:
    webui = WebuiRestartableBuilder(build_thread=_Threads().build, works_over=_works_over)

    assert str(webui) == "webui"


@pytest.mark.asyncio
async def test_each_build_serves_the_webui_on_a_thread_of_its_own(
    webui: WebuiRestartableBuilder,
) -> None:
    restartable = await webui.build()

    assert await _served(restartable.thread) == "ok"
    assert len(_webui_threads()) == 1


@pytest.mark.asyncio
async def test_a_webui_whose_thread_ended_serves_again_once_rebuilt(
    webui: WebuiRestartableBuilder,
) -> None:
    first = await webui.build()
    await first.thread.stop()

    second = await webui.build()

    assert [first.thread.is_alive(), second.thread.is_alive()] == [False, True]
    assert await _served(second.thread) == "ok"


@pytest.mark.asyncio
async def test_a_close_stops_its_thread(webui: WebuiRestartableBuilder) -> None:
    restartable = await webui.build()

    await restartable.close()

    assert _webui_threads() == []


@pytest.mark.asyncio
async def test_a_build_cut_while_its_thread_binds_stops_that_thread(
    *, threads: _Threads, webui: WebuiRestartableBuilder
) -> None:
    building = asyncio.create_task(webui.build())
    await asyncio.sleep(0)  # noqa: TID251  # the thread starts, the build waits for its bind

    building.cancel()
    with pytest.raises(asyncio.CancelledError):
        await building

    assert len(threads.built) == 1
    assert _webui_threads() == []


@pytest.mark.asyncio
async def test_a_build_on_a_port_held_elsewhere_raises_nothing_and_its_watch_finds_it_ended() -> (
    None
):
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        webui = WebuiRestartableBuilder(
            build_thread=_Threads(holder.getsockname()).build,
            works_over=lambda thread: webui_thread_watch_over(
                thread, monotonic_clock=FakeTime().monotonic
            ),
        )

        restartable = await webui.build()
        await restartable.close()  # waits for the thread the failed bind ended

    [watch] = restartable.works()
    with pytest.raises(WebuiThreadEndedError):
        await watch.work.run_once()


@pytest.mark.asyncio
async def test_the_watch_over_a_thread_looks_at_it_named_webui(threads: _Threads) -> None:
    webui = WebuiRestartableBuilder(
        build_thread=threads.build,
        works_over=lambda thread: webui_thread_watch_over(
            thread, monotonic_clock=FakeTime().monotonic
        ),
    )

    [watch] = (await webui.build()).works()

    await watch.work.run_once()  # its thread serves
    assert str(watch.work) == "webui"
    # Its turn awaits nothing: its time limit is the margin alone.
    assert watch.time_limit == timedelta(minutes=5)
