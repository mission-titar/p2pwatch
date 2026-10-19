"""``FakeDownloadClient``: the guard that refuses I/O before a login, as the real adapter does."""

import pytest

from p2pwatch.ports.driven.client_errors import ClientUnreachableError
from p2pwatch_testing.application.download_fakes import FakeDownloadClient


@pytest.mark.asyncio
async def test_a_disconnected_client_refuses_io_until_it_connects() -> None:
    client = FakeDownloadClient(disconnected=True)

    with pytest.raises(ClientUnreachableError, match="not connected"):
        await client.downloads()
    await client.connect()

    assert await client.downloads() == ()
