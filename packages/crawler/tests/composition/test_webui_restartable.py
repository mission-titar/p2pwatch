"""The webui as the node rebuilds it: the old thread stopped, the webui served on a thread built
anew, the watch over it handed back; the node's shutdown stops the thread held then."""

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
from p2pwatch.composition.webui_restartable import WebuiRestartable, webui_thread_watch_over
from p2pwatch.domain.work_dependencies import webui_dependency
from tests.contracts.application.ports.driven.restartable_contract import RestartableContract
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
    return [SupervisedWork(work=_Over(thread), time_limit=timedelta(minutes=5), dependencies=())]


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


@pytest_asyncio.fixture
async def webui(threads: _Threads) -> WebuiRestartable:
    """A webui whose first thread serves, its works ``_works_over``."""
    webui = WebuiRestartable(threads.build(), build_thread=threads.build, works_over=_works_over)
    await threads.built[0].start()
    return webui


def _webui_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == "webui"]


async def _served(thread: UvicornServerThread) -> str:
    host, port = thread.bound_address
    async with httpx.AsyncClient() as http:
        return (await http.get(f"http://{host}:{port}/")).text


class TestWebuiRestartable(RestartableContract):
    @pytest.fixture
    def restartable(self, *, threads: _Threads, webui: WebuiRestartable) -> WebuiRestartable:
        self._threads = threads
        return webui

    def state_of(self, restartable: Restartable[object]) -> object:
        return self._threads.built[-1]

    def state_under(self, works: Sequence[object]) -> object:
        [supervised] = works
        assert isinstance(supervised, SupervisedWork)
        assert isinstance(supervised.work, _Over)
        return supervised.work.thread


def test_it_is_named_as_the_webui_s_part_is() -> None:
    threads = _Threads()
    webui = WebuiRestartable(threads.build(), build_thread=threads.build, works_over=_works_over)

    assert str(webui) == "webui"


@pytest.mark.asyncio
async def test_a_rebuild_stops_the_old_thread_and_serves_on_a_new_one(
    *, threads: _Threads, webui: WebuiRestartable
) -> None:
    await webui.rebuild()

    assert [thread.is_alive() for thread in threads.built] == [False, True]
    assert await _served(threads.built[-1]) == "ok"
    assert len(_webui_threads()) == 1


@pytest.mark.asyncio
async def test_a_webui_whose_thread_ended_serves_again_once_rebuilt(
    *, threads: _Threads, webui: WebuiRestartable
) -> None:
    await threads.built[0].stop()

    await webui.rebuild()

    assert [thread.is_alive() for thread in threads.built] == [False, True]
    assert await _served(threads.built[-1]) == "ok"


@pytest.mark.asyncio
async def test_a_close_stops_the_thread_held_then(webui: WebuiRestartable) -> None:
    await webui.rebuild()

    await webui.close()

    assert _webui_threads() == []


@pytest.mark.asyncio
async def test_a_rebuild_on_a_port_held_elsewhere_raises_nothing_and_its_watch_finds_it_ended() -> (
    None
):
    webui_part = webui_dependency()
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        threads = _Threads(holder.getsockname())
        webui = WebuiRestartable(
            threads.build(),
            build_thread=threads.build,
            works_over=lambda thread: webui_thread_watch_over(
                thread, dependency=webui_part, monotonic_clock=FakeTime().monotonic
            ),
        )
        await threads.built[0].start()

        [watch] = await webui.rebuild()
        await webui.close()  # waits for the thread the failed bind ended

    with pytest.raises(WebuiThreadEndedError):
        await watch.work.run_once()


@pytest.mark.asyncio
async def test_the_watch_handed_back_looks_at_the_thread_built_anew(threads: _Threads) -> None:
    webui_part = webui_dependency()
    webui = WebuiRestartable(
        threads.build(),
        build_thread=threads.build,
        works_over=lambda thread: webui_thread_watch_over(
            thread, dependency=webui_part, monotonic_clock=FakeTime().monotonic
        ),
    )
    await threads.built[0].start()

    [watch] = await webui.rebuild()

    await watch.work.run_once()  # the old thread has ended, the new one serves
    assert (str(watch.work), watch.dependencies) == ("webui", (webui_part,))
    # Its turn awaits nothing: its time limit is the margin alone.
    assert watch.time_limit == timedelta(minutes=5)
