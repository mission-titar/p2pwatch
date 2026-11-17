"""The aMule client as the node rebuilds it: the old session logged out, a client built anew
logged in, the works over it handed back; the node's shutdown closes the client held then."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.amule_client_restartable import AmuleClientRestartable
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.identifiers import ClientName
from tests.contracts.application.ports.driven.restartable_contract import RestartableContract
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi

_AMULED = ClientName("amuled")


class _Over(Work):
    """A work over one client, never run."""

    def __init__(self, client: AmuleApiClient) -> None:
        self.client = client

    def __str__(self) -> str:
        return "status reading amuled"

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


class _Clients:
    """Builds clients of one fake aMule, keeping each, as the composition builds them."""

    def __init__(self) -> None:
        self.api = FakeAmuleApi()
        self.password = PASSWORD
        self.built: list[AmuleApiClient] = []

    def build(self) -> AmuleApiClient:
        search_start_store = FakeSearchStartStore()
        self.built.append(
            AmuleApiClient(
                "amuled.test",
                client_name=_AMULED,
                port=4711,
                password=self.password,
                timeout_seconds=10.0,
                request_bound_seconds=60.0,
                page_size=500,
                progress_poll_interval=timedelta(seconds=5),
                transport_factory=self.api.transport,
                monotonic_clock=self.api.monotonic_clock,
                wall_clock=FakeTime().wall,
                search_start_writer=search_start_store,
                search_start_reader=search_start_store,
            )
        )
        return self.built[-1]

    def restartable(self) -> AmuleClientRestartable:
        return AmuleClientRestartable(
            self.build(), client_name=_AMULED, build_client=self.build, works_over=_works_over
        )


def _works_over(client: AmuleApiClient, /) -> Sequence[SupervisedWork]:
    return [SupervisedWork(work=_Over(client), time_limit=timedelta(minutes=1), components=())]


def _client_under(works: Sequence[object]) -> AmuleApiClient:
    [supervised] = works
    assert isinstance(supervised, SupervisedWork)
    assert isinstance(supervised.work, _Over)
    return supervised.work.client


class TestAmuleClientRestartable(RestartableContract):
    @pytest.fixture
    def restartable(self) -> AmuleClientRestartable:
        self._clients = _Clients()
        return self._clients.restartable()

    def state_of(self, restartable: Restartable[object]) -> object:
        return self._clients.built[-1]

    def state_under(self, works: Sequence[object]) -> object:
        return _client_under(works)


def test_it_is_named_as_the_client_s_part_is() -> None:
    assert str(_Clients().restartable()) == "client amuled"


@pytest.mark.asyncio
async def test_a_rebuild_logs_the_old_session_out_and_a_new_one_in() -> None:
    clients = _Clients()
    restartable = clients.restartable()
    await clients.built[0].open()

    await restartable.rebuild()

    assert (clients.api.logins, clients.api.logouts) == (2, 1)


@pytest.mark.asyncio
async def test_a_close_logs_out_the_client_held_then() -> None:
    clients = _Clients()
    restartable = clients.restartable()
    await restartable.rebuild()

    await restartable.close()

    assert (clients.api.logins, clients.api.logouts) == (1, 1)


@pytest.mark.asyncio
async def test_a_refused_login_raises_and_the_next_rebuild_builds_a_client_anew() -> None:
    clients = _Clients()
    restartable = clients.restartable()
    clients.password = "wrong"
    with pytest.raises(ClientAuthError):
        await restartable.rebuild()

    clients.password = PASSWORD
    works = await restartable.rebuild()

    assert len(clients.built) == 3
    assert _client_under(works) is clients.built[2]
    assert clients.api.logins == 1
