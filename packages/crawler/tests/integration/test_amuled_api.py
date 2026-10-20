"""Login, refused login, network status and a search, against a REAL amuleapi.

Dedicated run: uv run pytest -m api_integration --no-cov
Without eD2k access the results are empty: what is validated is the cycle, not their richness.
"""

import httpx
import pytest

from p2pwatch.adapters.driven.monotonic_clock_asyncio import AsyncioMonotonicClock
from p2pwatch.adapters.driven.mule_api.client import AmuleApiClient
from p2pwatch.adapters.driven.mule_api.errors import ApiAuthError, ApiRejectedError
from tests.integration.conftest import ApiEndpoint

pytestmark = pytest.mark.api_integration


@pytest.mark.asyncio
async def test_real_login_succeeds(amuled: ApiEndpoint) -> None:
    client = AmuleApiClient(
        amuled.host,
        amuled.port,
        amuled.password,
        timeout_seconds=30.0,
        monotonic_clock=AsyncioMonotonicClock(),
        transport_factory=httpx.AsyncHTTPTransport,
    )
    await client.status()  # its login accepts the admin password written by --set-admin-pass
    await client.close()


@pytest.mark.asyncio
async def test_real_login_fails_with_wrong_password(amuled: ApiEndpoint) -> None:
    client = AmuleApiClient(
        amuled.host,
        amuled.port,
        "wrong-password",
        timeout_seconds=30.0,
        monotonic_clock=AsyncioMonotonicClock(),
        transport_factory=httpx.AsyncHTTPTransport,
    )
    with pytest.raises(ApiAuthError):
        await client.status()


@pytest.mark.asyncio
async def test_real_status(amuled: ApiEndpoint) -> None:
    client = AmuleApiClient(
        amuled.host,
        amuled.port,
        amuled.password,
        timeout_seconds=30.0,
        monotonic_clock=AsyncioMonotonicClock(),
        transport_factory=httpx.AsyncHTTPTransport,
    )
    try:
        status = await client.status()
        assert [channel.channel for channel in status.channels] == ["ed2k", "kad"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_search(amuled: ApiEndpoint) -> None:
    client = AmuleApiClient(
        amuled.host,
        amuled.port,
        amuled.password,
        timeout_seconds=30.0,
        monotonic_clock=AsyncioMonotonicClock(),
        transport_factory=httpx.AsyncHTTPTransport,
    )
    try:
        try:
            answer = await client.search("keroro", "ed2k", 30.0)
        except ApiRejectedError as exc:
            # The daemon refused the search cleanly (no eD2k server reachable from the
            # container): the request/response cycle IS validated, with its own message.
            assert str(exc)
            return
        assert isinstance(answer.reported_files, tuple)  # possibly empty: the call is what counts
    finally:
        await client.close()
