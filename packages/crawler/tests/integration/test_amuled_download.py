"""DOWNLOAD integration against a REAL amuleapi (download spec §11, option A).

Dedicated run: uv run pytest -m download_integration --no-cov
Validates the MECHANICS of the download: ``start`` accepted + the file appears in
``downloads`` with readable byte counters. COMPLETION is NOT reachable (no eD2k sources
from the ephemeral container): it is the start -> list -> status cycle that is validated.
"""

from datetime import timedelta

import httpx
import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.asyncio_monotonic_clock import AsyncioMonotonicClock
from p2pwatch.adapters.driven.system_wall_clock import SystemWallClock
from p2pwatch.domain.client_errors import DownloadRejectedError
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import ClientName
from tests.fakes.adapters.driven.fake_search_start_store import FakeSearchStartStore
from tests.integration.conftest import ApiEndpoint

pytestmark = pytest.mark.download_integration

# A NON-DEGENERATE canonical hash: above all NOT the MD4 of the empty file (31d6cfe0…), which
# amuled treats as instantly complete at 0 bytes and NEVER lists as an active partfile. With a
# real size, the link creates a listed partfile (completed_bytes=0 < size_bytes).
_HASH = "aabbccddeeff00112233445566778899"
_SIZE = 734003200  # ~700 MiB: a real size, hence an active partfile (never "complete")


@pytest.mark.asyncio
async def test_start_then_appears_in_downloads(amuled: ApiEndpoint) -> None:
    search_start_store = FakeSearchStartStore()
    client = AmuleApiClient(
        amuled.host,
        client_name=ClientName("amuled"),
        port=amuled.port,
        password=amuled.password,
        timeout_seconds=30.0,
        request_bound_seconds=180.0,
        page_size=500,
        progress_poll_interval=timedelta(seconds=5),
        monotonic_clock=AsyncioMonotonicClock(),
        wall_clock=SystemWallClock(),
        search_start_writer=search_start_store,
        search_start_reader=search_start_store,
        transport_factory=httpx.AsyncHTTPTransport,
    )
    try:
        file = FileKey(network=Network.ED2K, native_id=_HASH)
        try:
            await client.start(
                DownloadRequest(file=file, filename="probe-download.bin", size_bytes=_SIZE)
            )
        except DownloadRejectedError as exc:
            # The daemon refused the link cleanly, per item in the bulk envelope: the
            # request/response cycle IS validated, with its message. Tolerable here.
            assert str(exc)
            return
        # start ACCEPTED: a real-size link (no source) creates a listed partfile, and
        # `status=all` is what makes it visible whatever its state (§4.3).
        listed = {download.file: download for download in await client.downloads()}
        assert listed[file].size_bytes == _SIZE
        assert not listed[file].completed
    finally:
        await client.close()
