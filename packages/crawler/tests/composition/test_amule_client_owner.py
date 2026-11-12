"""The aMule client's owner: a restart closes its session and builds a client anew, then adds the
works holding it; the resource stack closes the client it holds then."""

from datetime import timedelta

import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.application.ports.driven.state_owner import StateOwner
from p2pwatch.application.steps.supervisor import SupervisedWork
from p2pwatch.application.steps.work import Work
from p2pwatch.composition.amule_client_owner import AmuleClientOwner
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.work_components import status_sensor_component
from tests.contracts.application.ports.driven.state_owner_contract import StateOwnerContract
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi

_AMULED = ClientName("amuled")


class _Holding(Work):
    """A work over one client, never run."""

    def __init__(self, client: AmuleApiClient) -> None:
        self.client = client

    def __str__(self) -> str:
        return "holding"

    async def wait_for_next_turn(self) -> None:
        """Never awaited."""

    async def run_once(self) -> None:
        """Never awaited."""


class _Owned:
    """An owner over a fake amuleapi, keeping each client it builds and the client each work
    added to the supervisor holds."""

    def __init__(self) -> None:
        self.api = FakeAmuleApi()
        self.password = PASSWORD
        self.built: list[AmuleApiClient] = []
        self.relied_on: list[object] = []
        self.owner = AmuleClientOwner(
            self._build(),
            client_name=_AMULED,
            build_client=self._build,
            build_works=self._works,
            add_work=self._add,
        )

    def _works(self, client: AmuleApiClient) -> list[SupervisedWork]:
        return [
            SupervisedWork(
                work=_Holding(client),
                time_limit=timedelta(minutes=1),
                feeds=(status_sensor_component(_AMULED),),
            )
        ]

    def _add(self, supervised: SupervisedWork) -> None:
        assert isinstance(supervised.work, _Holding)
        self.relied_on.append(supervised.work.client)

    def _build(self) -> AmuleApiClient:
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


class TestAmuleClientOwner(StateOwnerContract):
    @pytest.fixture
    def owner(self) -> AmuleClientOwner:
        self._owned = _Owned()
        return self._owned.owner

    def state_of(self, owner: StateOwner) -> object:
        return self._owned.built[-1]

    async def state_relied_on(self, owner: StateOwner) -> object:
        return self._owned.relied_on[-1]


def test_the_owner_is_named_after_its_client() -> None:
    assert str(_Owned().owner) == "owner of client amuled"


@pytest.mark.asyncio
async def test_a_restart_logs_the_old_session_out_and_a_new_one_in() -> None:
    owned = _Owned()
    await owned.built[0].open()

    await owned.owner.restart()

    assert (owned.api.logins, owned.api.logouts) == (2, 1)


@pytest.mark.asyncio
async def test_a_close_closes_the_client_held_then() -> None:
    owned = _Owned()
    await owned.owner.restart()

    await owned.owner.close()

    assert (owned.api.logins, owned.api.logouts) == (1, 1)


@pytest.mark.asyncio
async def test_a_refused_login_raises_adding_no_work_and_a_later_restart_builds_anew() -> None:
    owned = _Owned()
    owned.password = "wrong"
    with pytest.raises(ClientAuthError):
        await owned.owner.restart()
    assert owned.relied_on == []

    owned.password = PASSWORD
    await owned.owner.restart()

    assert owned.relied_on == [owned.built[-1]]
    assert owned.api.logins == 1
