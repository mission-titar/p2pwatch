import pytest

from p2pwatch.domain.status_reading import ClientStatus
from p2pwatch.ports.driven.client_status import StatusClient


class _StubClient:
    """Satisfies StatusClient structurally, without importing it."""

    async def status(self) -> ClientStatus:
        return ClientStatus(version=None, channels=())


@pytest.mark.asyncio
async def test_stub_client_satisfies_the_status_protocol() -> None:
    # The annotation makes mypy check the structural match.
    client: StatusClient = _StubClient()

    assert await client.status() == ClientStatus(version=None, channels=())
