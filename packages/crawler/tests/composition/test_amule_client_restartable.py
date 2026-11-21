"""The aMule client as the node builds it, at its start and at each rebuild: a client built anew
and logged in, with the works over it; its close logs its session out."""

from collections.abc import Sequence
from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.application.ports.driven.restartable import Restartable
from p2pwatch.application.steps.work import SupervisedWork, Work
from p2pwatch.composition.amule_client_restartable import (
    AmuleClientRestartable,
    AmuleClientRestartableBuilder,
)
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword
from tests.contracts.application.ports.driven.restartable_builder_contract import (
    RestartableBuilderContract,
)
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
    """Builds clients of one fake aMule on one timeline, as the composition builds them."""

    def __init__(self) -> None:
        self.time = FakeTime()
        self.api = FakeAmuleApi(monotonic_clock=self.time.monotonic)
        self.password = PASSWORD
        # One store for every client, as the composition's ``build_client`` closes over one.
        self.search_start_store = FakeSearchStartStore()

    def build(self) -> AmuleApiClient:
        return AmuleApiClient(
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
            wall_clock=self.time.wall,
            search_start_writer=self.search_start_store,
            search_start_reader=self.search_start_store,
        )

    def builder(self) -> AmuleClientRestartableBuilder:
        return AmuleClientRestartableBuilder(
            client_name=_AMULED, build_client=self.build, works_over=_works_over
        )


def _works_over(client: AmuleApiClient, /) -> Sequence[SupervisedWork]:
    return [SupervisedWork(work=_Over(client), time_limit=timedelta(minutes=1))]


class TestAmuleClientRestartableBuilder(RestartableBuilderContract):
    @pytest.fixture
    def restartable_builder(self) -> AmuleClientRestartableBuilder:
        return _Clients().builder()

    def state_of(self, restartable: Restartable[object]) -> object:
        assert isinstance(restartable, AmuleClientRestartable)
        return restartable.client

    def state_reached(self, restartable: Restartable[object]) -> object:
        [supervised] = restartable.works()
        assert isinstance(supervised, SupervisedWork)
        assert isinstance(supervised.work, _Over)
        return supervised.work.client


def test_it_names_its_clients_as_the_client_s_part_is() -> None:
    assert str(_Clients().builder()) == "client amuled"


@pytest.mark.asyncio
async def test_each_build_logs_a_client_of_its_own_in() -> None:
    clients = _Clients()
    builder = clients.builder()

    for _ in range(2):
        await builder.build()

    assert clients.api.logins == 2


@pytest.mark.asyncio
async def test_a_close_logs_its_session_out() -> None:
    clients = _Clients()
    restartable = await clients.builder().build()

    await restartable.close()

    assert (clients.api.logins, clients.api.logouts) == (1, 1)


@pytest.mark.asyncio
async def test_a_refused_login_builds_a_client_all_the_same() -> None:
    clients = _Clients()
    clients.password = "wrong"

    restartable = await clients.builder().build()

    # No rebuild in vain: the status reading alerts on the refusal, which no rebuild repairs.
    with pytest.raises(ClientAuthError):
        await restartable.client.status()


@pytest.mark.asyncio
async def test_a_client_built_anew_spaces_its_first_ed2k_search_from_the_one_built_before() -> None:
    clients = _Clients()
    builder = clients.builder()
    ed2k = Channel("ed2k")
    first = await builder.build()
    await first.client.search(Keyword("keroro"), channel=ed2k, budget_seconds=120.0)
    clients.time.advance(timedelta(seconds=20))

    second = await builder.build()
    await second.client.search(Keyword("titar"), channel=ed2k, budget_seconds=120.0)

    [before, after] = [started_at for started_at, _ in clients.api.searches.values()]
    assert after - before == timedelta(seconds=60)
