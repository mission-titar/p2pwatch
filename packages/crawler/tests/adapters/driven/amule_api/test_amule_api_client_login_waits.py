"""``AmuleApiClient`` after a refused login: every call refused at once, the next login 1 min
later, then twice as long each time, 30 min at most, under amuleapi's login limiter."""

import asyncio
import logging
from datetime import timedelta

import httpx
import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient, TransportFactory
from p2pwatch.adapters.driven.amule_api.errors import ApiAuthError
from p2pwatch.domain.client_errors import ClientAuthError
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi, error

_LOGIN = "/api/v1/auth/login"


def _client(
    api: FakeAmuleApi, *, time: FakeTime, transport_factory: TransportFactory | None = None
) -> AmuleApiClient:
    search_start_store = FakeSearchStartStore()
    return AmuleApiClient(
        "amuled.test",
        client_name=ClientName("amuled"),
        port=4711,
        password=PASSWORD,
        timeout_seconds=10.0,
        request_bound_seconds=60.0,
        page_size=500,
        progress_poll_interval=timedelta(seconds=5),
        transport_factory=transport_factory or api.transport,
        monotonic_clock=time.monotonic,
        wall_clock=time.wall,
        search_start_writer=search_start_store,
        search_start_reader=search_start_store,
    )


def _paths(api: FakeAmuleApi) -> list[str]:
    return [request.url.path for request in api.requests]


@pytest.mark.asyncio
async def test_a_call_after_a_refused_login_is_refused_at_once_without_asking() -> None:
    time = FakeTime()
    api = FakeAmuleApi(password="another", monotonic_clock=time.monotonic)
    client = _client(api, time=time)
    with pytest.raises(ClientAuthError):
        await client.status()
    time.advance(timedelta(seconds=59))

    with pytest.raises(ClientAuthError, match="the next login in 1 s"):
        await client.status()
    assert _paths(api) == [_LOGIN]


@pytest.mark.asyncio
async def test_open_tolerates_a_refused_password_in_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    time = FakeTime()
    api = FakeAmuleApi(password="another", monotonic_clock=time.monotonic)
    client = _client(api, time=time)

    with caplog.at_level(
        logging.WARNING, logger="p2pwatch.adapters.driven.amule_api.amule_api_client"
    ):
        await client.open()

    assert [record.getMessage() for record in caplog.records] == [
        "login refused at startup (amuleapi refused the admin password: the next login in 60 s): "
        "tolerated"
    ]


def _login_minutes(api: FakeAmuleApi, *, since: MonotonicInstant) -> list[float]:
    """When each login reached amuleapi, in minutes after ``since``."""
    return [
        (moment - since) / timedelta(minutes=1)
        for moment, request in api.calls
        if request.url.path == _LOGIN
    ]


@pytest.mark.asyncio
async def test_each_refused_login_doubles_the_wait_before_the_next_30_min_at_most() -> None:
    time = FakeTime()
    api = FakeAmuleApi(password="another", monotonic_clock=time.monotonic)
    client = _client(api, time=time)
    start = time.monotonic.now()

    for _ in range(130 * 6):  # a call every 10 s for 130 min, as the works make them
        with pytest.raises(ClientAuthError):
            await client.status()
        time.advance(timedelta(seconds=10))

    assert _login_minutes(api, since=start) == [0, 1, 3, 7, 15, 31, 61, 91, 121]


@pytest.mark.asyncio
async def test_a_call_after_a_refused_renewal_is_refused_at_once_without_asking() -> None:
    time = FakeTime()
    api = FakeAmuleApi(monotonic_clock=time.monotonic)
    client = _client(api, time=time)
    await client.open()
    # The password changed: amuleapi refuses the token, then the login renewing it.
    api.password = "another"
    api.overrides[("GET", "/api/v1/status")] = lambda _: error(401, code="unauthorized")
    with pytest.raises(ClientAuthError):
        await client.status()

    with pytest.raises(ClientAuthError, match="the next login in 60 s"):
        await client.status()
    assert _paths(api) == [_LOGIN, "/api/v1/status", _LOGIN]


@pytest.mark.asyncio
async def test_calls_whose_token_is_refused_together_try_one_login() -> None:
    time = FakeTime()
    api = FakeAmuleApi(monotonic_clock=time.monotonic)

    async def round_trip(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)  # each call sends before any is answered  # noqa: TID251
        return api.handle(request)

    transport = httpx.MockTransport(round_trip)
    client = _client(api, time=time, transport_factory=lambda: transport)
    await client.open()
    api.password = "another"
    api.overrides[("GET", "/api/v1/status")] = lambda _: error(401, code="unauthorized")

    outcomes = await asyncio.gather(client.status(), client.status(), return_exceptions=True)

    assert [type(outcome) for outcome in outcomes] == [ApiAuthError, ApiAuthError]
    assert _paths(api) == [_LOGIN, "/api/v1/status", "/api/v1/status", _LOGIN]


@pytest.mark.asyncio
async def test_a_login_accepted_brings_the_wait_after_the_next_refusal_back_to_1_min() -> None:
    time = FakeTime()
    api = FakeAmuleApi(password="another", monotonic_clock=time.monotonic)
    client = _client(api, time=time)
    start = time.monotonic.now()
    for _ in range(2):  # refused at 0 and 1 min: the next login waits 2 min
        with pytest.raises(ClientAuthError):
            await client.status()
        time.advance(timedelta(minutes=1))
    time.advance(timedelta(minutes=1))
    api.password = PASSWORD
    await client.status()
    # The password changed again: amuleapi refuses the token, then the login renewing it.
    api.password = "another"
    api.overrides[("GET", "/api/v1/status")] = lambda _: error(401, code="unauthorized")

    for _ in range(2):
        time.advance(timedelta(minutes=1))
        with pytest.raises(ClientAuthError):
            await client.status()

    assert _login_minutes(api, since=start) == [0, 1, 3, 4, 5]
