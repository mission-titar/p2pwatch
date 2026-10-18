"""``FakeAmuleApiServer``: the amuleapi fake served on a loopback socket."""

import httpx
import pytest

from p2pwatch.adapters.mule_api.client import AmuleApiClient
from p2pwatch_testing.adapters.mule_api.api_fakes import (
    PASSWORD,
    FakeAmuleApi,
    FakeAmuleApiServer,
)


@pytest.mark.asyncio
async def test_the_real_client_logs_in_and_out_over_the_socket() -> None:
    api = FakeAmuleApi()

    with FakeAmuleApiServer(api) as server:
        client = AmuleApiClient(
            server.host, server.port, PASSWORD, monotonic_clock=api.monotonic_clock
        )
        await client.connect()
        await client.close()

    assert (server.host, server.port != 0) == ("127.0.0.1", True)
    assert (api.logins, api.logouts) == (1, 1)


def test_a_request_the_fake_refuses_answers_500_and_fails_the_exit() -> None:
    api = FakeAmuleApi()
    server = FakeAmuleApiServer(api)

    with pytest.raises(KeyError, match="nope"), server:
        response = httpx.get(f"http://{server.host}:{server.port}/api/v1/nope")

    assert response.status_code == 500
