"""The webui thread's owner: a restart stops the old thread and serves the webui on a thread built
anew, then adds the works over it; the resource stack stops the thread it holds then."""

import threading
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
import pytest_asyncio
from starlette.applications import Starlette

from p2pwatch.adapters.driving.webui.uvicorn_server_thread import UvicornServerThread
from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.application.steps.supervisor import SupervisedWork
from p2pwatch.application.steps.work import Work
from p2pwatch.composition.webui_thread_owner import WebuiThreadOwner
from p2pwatch.domain.work_components import webui_component
from tests.contracts.application.ports.driven.state_owner_contract import StateOwnerContract


class _Holding(Work):
    """A work over one webui thread, never run."""

    def __init__(self, thread: UvicornServerThread) -> None:
        self.thread = thread

    def __str__(self) -> str:
        return "holding"

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


class _Owned:
    """An owner keeping each thread it builds and the thread each work added to the supervisor
    holds."""

    def __init__(self) -> None:
        self.built: list[UvicornServerThread] = []
        self.relied_on: list[UvicornServerThread] = []
        self.owner = WebuiThreadOwner(
            self._build(),
            build_thread=self._build,
            build_works=self._works,
            add_work=self._add,
        )

    def _works(self, thread: UvicornServerThread) -> list[SupervisedWork]:
        return [
            SupervisedWork(
                work=_Holding(thread), time_limit=timedelta(minutes=1), feeds=(webui_component(),)
            )
        ]

    def _add(self, supervised: SupervisedWork) -> None:
        assert isinstance(supervised.work, _Holding)
        self.relied_on.append(supervised.work.thread)

    def _build(self) -> UvicornServerThread:
        self.built.append(
            UvicornServerThread(
                Starlette(),
                address=("127.0.0.1", 0),
                start_timeout_seconds=5.0,
                join_timeout_seconds=5.0,
                serving_resources=(),
            )
        )
        return self.built[-1]


@pytest_asyncio.fixture
async def owned() -> AsyncIterator[_Owned]:
    """An owner serving its first thread, stopped at the end."""
    owned = _Owned()
    await owned.built[0].start()
    yield owned
    await owned.owner.close()


def _webui_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == "webui"]


class TestWebuiThreadOwner(StateOwnerContract):
    @pytest.fixture
    def owner(self, owned: _Owned) -> WebuiThreadOwner:
        self._owned = owned
        return owned.owner

    def state_of(self, owner: StateOwner) -> object:
        return self._owned.built[-1]

    async def state_relied_on(self, owner: StateOwner) -> object:
        return self._owned.relied_on[-1]


def test_the_owner_is_named_after_its_thread() -> None:
    assert str(_Owned().owner) == "webui thread"


@pytest.mark.asyncio
async def test_a_restart_stops_the_old_thread_and_serves_on_a_new_one(owned: _Owned) -> None:
    await owned.owner.restart()

    old, new = owned.built
    assert (old.is_alive(), new.is_alive()) == (False, True)
    assert len(_webui_threads()) == 1


@pytest.mark.asyncio
async def test_a_close_stops_the_thread_held_then(owned: _Owned) -> None:
    await owned.owner.restart()

    await owned.owner.close()

    assert _webui_threads() == []
