"""``FakeAmuleApiServer``: the amuleapi fake served on a loopback socket."""

import threading
from datetime import timedelta

import httpx
import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from tests.fakes.fake_amule_api import PASSWORD, FakeAmuleApi
from tests.fakes.fake_amule_api_server import FakeAmuleApiServer


@pytest.mark.asyncio
async def test_the_real_client_logs_in_and_out_over_the_socket() -> None:
    api = FakeAmuleApi()

    with FakeAmuleApiServer(api) as server:
        client = AmuleApiClient(
            server.host,
            port=server.port,
            password=PASSWORD,
            timeout_seconds=10.0,
            page_size=500,
            progress_poll_interval=timedelta(seconds=5),
            transport_factory=httpx.AsyncHTTPTransport,
            monotonic_clock=api.monotonic_clock,
        )
        await client.open()
        await client.close()

    assert (server.host, server.port != 0) == ("127.0.0.1", True)
    assert (api.logins, api.logouts) == (1, 1)


def test_a_request_the_fake_refuses_answers_500_and_fails_the_exit() -> None:
    api = FakeAmuleApi()
    server = FakeAmuleApiServer(api)

    with pytest.raises(KeyError, match="nope"), server:
        response = httpx.get(f"http://{server.host}:{server.port}/api/v1/nope")

    assert response.status_code == 500


def test_wait_for_returns_once_a_request_makes_the_predicate_hold() -> None:
    api = FakeAmuleApi()

    with FakeAmuleApiServer(api) as server:
        login = threading.Thread(
            target=httpx.post,
            args=(f"http://{server.host}:{server.port}/api/v1/auth/login?include_token=true",),
            kwargs={"json": {"password": PASSWORD}},
        )
        login.start()
        assert server.wait_for(lambda seen: seen.logins == 1, timeout_seconds=5.0)
        login.join()


def test_wait_for_gives_up_after_its_timeout() -> None:
    with FakeAmuleApiServer(FakeAmuleApi()) as server:
        assert not server.wait_for(lambda seen: seen.logins == 1, timeout_seconds=0.01)
