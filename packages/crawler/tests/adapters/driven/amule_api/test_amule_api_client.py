"""``AmuleApiClient``: auth, search, status, downloads (spec amuleapi §4)."""

import asyncio
import json
import logging
from datetime import timedelta
from typing import cast

import httpx
import pytest

from p2pwatch.adapters.driven.amule_api.amule_api_client import AmuleApiClient
from p2pwatch.adapters.driven.amule_api.errors import ApiAuthError, ApiUnreachableError
from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.application.ports.driven.source_client import SourceClient
from p2pwatch.domain.client_errors import (
    ClientUnreachableError,
    DownloadRejectedError,
    ReadRejectedError,
    SearchFailedError,
)
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import Channel, Keyword
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.source import ContactPoint, SourceRole
from p2pwatch.domain.status_reading import ChannelStatus
from tests.fakes.fake_amule_api import PASSWORD, TOKEN, FakeAmuleApi, error

_HASH = "8b54a3c20fae9e4b9f7e0c2c8c01b6b1"
_KEY = FileKey(network=Network.ED2K, native_id=_HASH)


_PAGE_SIZE = 500
_PROGRESS_POLL_INTERVAL = timedelta(seconds=5)


def _client(
    api: FakeAmuleApi,
    *,
    password: str = PASSWORD,
    page_size: int = _PAGE_SIZE,
    progress_poll_interval: timedelta = _PROGRESS_POLL_INTERVAL,
) -> AmuleApiClient:
    return AmuleApiClient(
        "amuled.test",
        port=4711,
        password=password,
        timeout_seconds=10.0,
        page_size=page_size,
        progress_poll_interval=progress_poll_interval,
        transport_factory=api.transport,
        monotonic_clock=api.monotonic_clock,
    )


async def _connected(
    api: FakeAmuleApi,
    *,
    page_size: int = _PAGE_SIZE,
    progress_poll_interval: timedelta = _PROGRESS_POLL_INTERVAL,
) -> AmuleApiClient:
    client = _client(api, page_size=page_size, progress_poll_interval=progress_poll_interval)
    await client.open()
    return client


def _paths(api: FakeAmuleApi, path: str) -> list[httpx.URL]:
    """Every request made to one route, in order (close() adds a logout after the assertions)."""
    return [request.url for request in api.requests if request.url.path == path]


def _seconds_after_start(api: FakeAmuleApi, method: str, path: str) -> list[float]:
    """When each call to one route was made, in seconds after the search's network start."""
    assert api.search_started_at is not None
    start: MonotonicInstant = api.search_started_at
    return [
        (moment - start).total_seconds()
        for moment, request in api.calls
        if request.method == method and request.url.path == path
    ]


def _progress_polls(api: FakeAmuleApi) -> list[float]:
    """The reads asking for no row: the polls of the progress envelope."""
    assert api.search_started_at is not None
    return [
        (moment - api.search_started_at).total_seconds()
        for moment, request in api.calls
        if request.url.path == "/api/v1/search/42/results"
        and request.url.params.get("limit") == "0"
    ]


def _result(name: str = "Keroro.095.avi") -> dict[str, object]:
    return {"hash": _HASH, "name": name, "size_bytes": 10, "sources": {"total": 1}}


@pytest.mark.asyncio
async def test_a_first_call_logs_in_and_arms_the_bearer() -> None:
    api = FakeAmuleApi()
    client = _client(api)
    try:
        await client.status()
    finally:
        await client.close()

    login = api.requests[0]
    assert login.url.path == "/api/v1/auth/login"
    # The token has to be asked for: the default reply carries only the cookie (spec §6).
    assert login.url.params.get("include_token") == "true"
    assert api.requests[1].headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.asyncio
async def test_calls_share_one_login() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)
    await client.status()
    await client.status()
    await client.close()

    assert api.logins == 1


def _yielding_client(api: FakeAmuleApi) -> AmuleApiClient:
    """A client whose every request suspends like a real one, letting the other callers in."""

    async def round_trip(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)  # noqa: TID251
        return api.handle(request)

    transport = httpx.MockTransport(round_trip)
    return AmuleApiClient(
        "amuled.test",
        port=4711,
        password=PASSWORD,
        timeout_seconds=10.0,
        page_size=_PAGE_SIZE,
        progress_poll_interval=_PROGRESS_POLL_INTERVAL,
        transport_factory=lambda: transport,
        monotonic_clock=api.monotonic_clock,
    )


@pytest.mark.asyncio
async def test_concurrent_first_calls_log_in_once() -> None:
    api = FakeAmuleApi()
    client = _yielding_client(api)
    await asyncio.gather(*(client.status() for _ in range(5)))
    await client.close()

    assert api.logins == 1  # one session: no AsyncClient opened for nothing


@pytest.mark.asyncio
async def test_an_empty_password_is_refused_without_asking() -> None:
    api = FakeAmuleApi()
    client = _client(api, password="")

    with pytest.raises(ApiAuthError):
        await client.status()
    assert api.requests == []


@pytest.mark.asyncio
async def test_a_wrong_password_is_a_config_error_not_a_loop_case() -> None:
    api = FakeAmuleApi()
    client = _client(api, password="wrong")

    with pytest.raises(ApiAuthError):
        await client.status()


@pytest.mark.asyncio
async def test_a_login_reply_without_a_token_is_a_config_error() -> None:
    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/auth/login")] = lambda _: httpx.Response(
        200, json={"role": "admin"}
    )
    client = _client(api)

    with pytest.raises(ApiAuthError):
        await client.status()


@pytest.mark.asyncio
async def test_login_disabled_is_a_daemon_that_is_not_ready() -> None:
    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/auth/login")] = lambda _: error(
        503, code="login_disabled", message="no password configured"
    )
    client = _client(api)

    with pytest.raises(ApiUnreachableError):
        await client.status()


@pytest.mark.asyncio
async def test_a_dead_transport_is_an_unreachable_daemon() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/auth/login")] = refuse
    client = _client(api)

    with pytest.raises(ApiUnreachableError):
        await client.status()


@pytest.mark.asyncio
async def test_close_logs_out_once_and_tolerates_a_failure() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)
    api.overrides[("POST", "/api/v1/auth/logout")] = lambda _: error(401, code="unauthorized")

    await client.close()
    await client.close()  # a second close is a no-op, not a second request

    assert [request.url.path for request in api.requests].count("/api/v1/auth/logout") == 1


@pytest.mark.asyncio
async def test_a_call_after_close_raises_instead_of_logging_in_again() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)
    await client.close()

    with pytest.raises(ApiUnreachableError, match="closed"):
        await client.status()
    assert api.logins == 1  # nothing would revoke a session opened past the shutdown


@pytest.mark.asyncio
async def test_a_close_during_a_login_revokes_the_session_it_opened() -> None:
    api = FakeAmuleApi()
    login_reached, login_released = asyncio.Event(), asyncio.Event()

    async def round_trip(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/login":
            login_reached.set()
            await login_released.wait()
        return api.handle(request)

    transport = httpx.MockTransport(round_trip)
    client = AmuleApiClient(
        "amuled.test",
        port=4711,
        password=PASSWORD,
        timeout_seconds=10.0,
        page_size=_PAGE_SIZE,
        progress_poll_interval=_PROGRESS_POLL_INTERVAL,
        transport_factory=lambda: transport,
        monotonic_clock=api.monotonic_clock,
    )
    call = asyncio.create_task(client.status())
    await login_reached.wait()
    closing = asyncio.create_task(client.close())
    await asyncio.sleep(0)  # close() runs while the login is held  # noqa: TID251
    login_released.set()
    outcomes = await asyncio.gather(call, closing, return_exceptions=True)

    assert (api.logins, api.logouts) == (1, 1), outcomes


@pytest.mark.asyncio
async def test_a_401_answered_during_close_logs_in_no_more() -> None:
    api = FakeAmuleApi()
    status_reached, status_released = asyncio.Event(), asyncio.Event()
    logout_reached, logout_released = asyncio.Event(), asyncio.Event()

    async def round_trip(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/status":
            status_reached.set()
            await status_released.wait()
            return error(401, code="unauthorized")
        if request.url.path == "/api/v1/auth/logout":
            logout_reached.set()
            await logout_released.wait()
        return api.handle(request)

    transport = httpx.MockTransport(round_trip)
    client = AmuleApiClient(
        "amuled.test",
        port=4711,
        password=PASSWORD,
        timeout_seconds=10.0,
        page_size=_PAGE_SIZE,
        progress_poll_interval=_PROGRESS_POLL_INTERVAL,
        transport_factory=lambda: transport,
        monotonic_clock=api.monotonic_clock,
    )
    await client.open()
    call = asyncio.create_task(client.status())
    await status_reached.wait()
    closing = asyncio.create_task(client.close())
    await logout_reached.wait()  # closed, its session not yet dropped
    status_released.set()

    with pytest.raises(ApiUnreachableError, match="closed"):
        await call
    logout_released.set()
    await closing
    assert api.logins == 1  # a token minted now would never be revoked


@pytest.mark.asyncio
async def test_open_logs_in() -> None:
    api = FakeAmuleApi()
    client = _client(api)

    await client.open()

    assert api.logins == 1


@pytest.mark.asyncio
async def test_a_call_after_a_tolerated_unreachable_open_logs_in_and_succeeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/auth/login")] = refuse
    client = _client(api)

    with caplog.at_level(
        logging.WARNING, logger="p2pwatch.adapters.driven.amule_api.amule_api_client"
    ):
        await client.open()

    assert [record.getMessage() for record in caplog.records] == [
        "amuled unreachable at startup (POST /auth/login: connection refused): tolerated, "
        "the loops retry"
    ]
    del api.overrides[("POST", "/api/v1/auth/login")]
    await client.status()  # the session opens once the daemon listens
    assert api.logins == 1


@pytest.mark.asyncio
async def test_a_session_opened_after_a_failed_login_gets_a_transport_of_its_own() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/auth/login")] = refuse
    transports: list[httpx.MockTransport] = []

    def transport_factory() -> httpx.MockTransport:
        transports.append(api.transport())
        return transports[-1]

    client = AmuleApiClient(
        "amuled.test",
        port=4711,
        password=PASSWORD,
        timeout_seconds=10.0,
        page_size=_PAGE_SIZE,
        progress_poll_interval=_PROGRESS_POLL_INTERVAL,
        transport_factory=transport_factory,
        monotonic_clock=api.monotonic_clock,
    )
    await client.open()
    del api.overrides[("POST", "/api/v1/auth/login")]
    await client.status()
    await client.close()

    # The failed login closed its session, and the transport with it.
    assert len(transports) == 2


@pytest.mark.asyncio
async def test_open_lets_a_refused_password_through() -> None:
    client = _client(FakeAmuleApi(), password="wrong")

    with pytest.raises(ApiAuthError):
        await client.open()


@pytest.mark.asyncio
async def test_a_stale_token_is_renewed_once() -> None:
    """§7.3: a 401 is terminal for the session, so we re-login once and never loop."""
    api = FakeAmuleApi()
    client = await _connected(api)
    stale = {"count": 0}

    def once(request: httpx.Request) -> httpx.Response:
        stale["count"] += 1
        if stale["count"] == 1:
            return error(401, code="unauthorized", message="credentials changed")
        return httpx.Response(200, json=api.status)

    api.overrides[("GET", "/api/v1/status")] = once
    await client.status()
    await client.close()

    assert api.logins == 2
    assert stale["count"] == 2


@pytest.mark.asyncio
async def test_a_second_401_ends_the_session_instead_of_looping() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)
    api.overrides[("GET", "/api/v1/status")] = lambda _: error(401, code="unauthorized")

    with pytest.raises(ApiUnreachableError):
        await client.status()
    # One re-login, one retry, then it stops: the limiter locks an IP out after 30 rejects.
    assert api.logins == 2
    assert [request.url.path for request in api.requests].count("/api/v1/status") == 2


@pytest.mark.asyncio
async def test_calls_rejected_together_renew_the_token_once() -> None:
    """A daemon restart rejects every call in flight: one login renews them all."""
    api = FakeAmuleApi()
    client = _yielding_client(api)
    await client.open()
    rejected = {"count": 0}

    def stale_twice(request: httpx.Request) -> httpx.Response:
        rejected["count"] += 1
        if rejected["count"] <= 2:
            return error(401, code="unauthorized", message="amuleapi restarted")
        return httpx.Response(200, json=api.status)

    api.overrides[("GET", "/api/v1/status")] = stale_twice
    await asyncio.gather(client.status(), client.status())
    await client.close()

    assert api.logins == 2  # the first session's, then one renewal for both calls


@pytest.mark.asyncio
async def test_a_body_that_is_not_json_is_an_unreachable_daemon() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)
    api.overrides[("GET", "/api/v1/status")] = lambda _: httpx.Response(200, content=b"<html>")

    with pytest.raises(ApiUnreachableError):
        await client.status()


# --- search(): one call per search ---------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("channel", "search_type"), [("ed2k", "global"), ("kad", "kad")])
async def test_search_starts_the_keyword_on_the_channels_search_type(
    channel: Channel, search_type: str
) -> None:
    api = FakeAmuleApi()
    client = await _connected(api)

    await client.search(Keyword("keroro"), channel=channel, budget_seconds=120)
    await client.close()

    start = api.requests[1]
    assert start.url.path == "/api/v1/search"
    assert json.loads(start.content) == {"query": "keroro", "type": search_type}


def test_the_client_declares_the_channels_it_searches() -> None:
    assert _client(FakeAmuleApi()).channels() == ("ed2k", "kad")


@pytest.mark.asyncio
async def test_search_answers_the_results_with_their_keyword_and_counts_what_it_drops() -> None:
    rows = [_result(f"Keroro.{index:04d}.avi") | {"hash": f"{index:032x}"} for index in range(501)]
    api = FakeAmuleApi(results=[*rows, {"hash": "nope"}])
    client = await _connected(api)

    answer = await client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=120)
    await client.close()

    assert len(answer.reported_files) == 501
    assert {reported_file.keyword for reported_file in answer.reported_files} == {"keroro"}
    assert answer.skipped_result_count == 1


@pytest.mark.asyncio
async def test_search_returns_as_soon_as_amuled_reports_it_finished() -> None:
    api = FakeAmuleApi(search_seconds={"keroro": 12})
    client = await _connected(api)

    await client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=120)
    await client.close()

    assert _progress_polls(api) == [0, 5, 10, 15]


@pytest.mark.asyncio
async def test_search_reads_its_progress_at_the_poll_interval_it_was_given() -> None:
    api = FakeAmuleApi(search_seconds={"keroro": 7})
    client = await _connected(api, progress_poll_interval=timedelta(seconds=3))

    await client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=120)
    await client.close()

    assert _progress_polls(api) == [0, 3, 6, 9]


@pytest.mark.asyncio
async def test_search_stops_waiting_at_its_budget_and_returns_what_it_holds() -> None:
    api = FakeAmuleApi(progress={"state": "running"}, results=[_result()])
    client = await _connected(api)

    answer = await client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=12)
    await client.close()

    assert _progress_polls(api) == [0, 5, 10, 12]
    assert len(answer.reported_files) == 1


@pytest.mark.asyncio
async def test_search_never_stops_nor_frees_its_search() -> None:
    """amuled expires a Kad search at 45 s, and stopping one takes it off Kad's list."""
    api = FakeAmuleApi(progress={"state": "running"})
    client = await _connected(api)

    await client.search(Keyword("keroro"), channel=Channel("kad"), budget_seconds=120)
    await client.close()

    assert _paths(api, "/api/v1/search/42/stop") == []
    assert [request for request in api.requests if request.method == "DELETE"] == []


@pytest.mark.asyncio
async def test_a_kad_search_is_widened_from_its_second_poll_until_kad_refuses() -> None:
    api = FakeAmuleApi(progress={"state": "running"})
    answers = [httpx.Response(202)] * 4 + [error(409, code="kad_more_exhausted")]
    api.overrides[("POST", "/api/v1/search/42/more")] = lambda _: answers.pop(0)
    client = await _connected(api)

    await client.search(Keyword("keroro"), channel=Channel("kad"), budget_seconds=120)
    await client.close()

    assert _seconds_after_start(api, "POST", "/api/v1/search/42/more") == [5, 10, 15, 20, 25]


@pytest.mark.asyncio
async def test_an_ed2k_search_is_never_widened() -> None:
    api = FakeAmuleApi(progress={"state": "running"})
    client = await _connected(api)

    await client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=120)
    await client.close()

    assert _paths(api, "/api/v1/search/42/more") == []


@pytest.mark.asyncio
async def test_a_failed_widening_leaves_the_search_standing() -> None:
    """A reask on a search already finished answers 400 bad_request, an unreachable daemon."""
    api = FakeAmuleApi(progress={"state": "running"}, results=[_result()])
    api.overrides[("POST", "/api/v1/search/42/more")] = lambda _: error(400, code="bad_request")
    client = await _connected(api)

    answer = await client.search(Keyword("keroro"), channel=Channel("kad"), budget_seconds=120)
    await client.close()

    assert len(answer.reported_files) == 1
    assert len(_paths(api, "/api/v1/search/42/more")) == 1


@pytest.mark.asyncio
async def test_a_search_the_daemon_refuses_fails_its_channel() -> None:
    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/search")] = lambda _: error(
        400, code="amuled_rejected", message="not connected to any server"
    )
    client = await _connected(api)

    with pytest.raises(SearchFailedError, match="not connected to any server") as raised:
        await client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=120)
    assert type(raised.value) is SearchFailedError


@pytest.mark.asyncio
async def test_a_search_reply_without_an_id_fails_its_channel() -> None:
    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/search")] = lambda _: httpx.Response(202, json={"query": "k"})
    client = await _connected(api)

    with pytest.raises(SearchFailedError):
        await client.search(Keyword("keroro"), channel=Channel("ed2k"), budget_seconds=120)


# --- status ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_reads_the_channels_and_the_daemon_version() -> None:
    api = FakeAmuleApi(
        status={
            "ec_connected": True,
            "ed2k": {"state": "connected", "high_id": False},
            "kad": {"state": "connecting"},
        },
        version={"daemon_version": "GIT rev. 3.0.1-773-g500293ba3"},
    )
    client = await _connected(api)

    status = await client.status()
    await client.close()

    assert status.version == "GIT rev. 3.0.1-773-g500293ba3"
    assert status.channels == (
        ChannelStatus(channel=Channel("ed2k"), connected=True, connectable=False),
        ChannelStatus(channel=Channel("kad"), connected=False, connectable=None),
    )


@pytest.mark.parametrize("ec_connected", [{"ec_connected": False}, {}])
@pytest.mark.asyncio
async def test_status_without_amuled_behind_amuleapi_is_unreachable(
    ec_connected: dict[str, bool],
) -> None:
    # amuleapi answers from its cache with the last states: a dead amuled reads "connected".
    stale = {
        "ed2k": {"state": "connected", "high_id": True},
        "kad": {"state": "connected", "firewalled_tcp": False},
    }
    client = await _connected(FakeAmuleApi(status={**ec_connected, **stale}))

    with pytest.raises(ClientUnreachableError):
        await client.status()
    await client.close()


@pytest.mark.asyncio
async def test_a_status_the_daemon_refuses_is_a_refused_read() -> None:
    # A route a weekly aMule bump renamed: /version answers 404 not_found.
    api = FakeAmuleApi(status={"ec_connected": True})
    api.overrides[("GET", "/api/v1/version")] = lambda _: error(
        404, code="not_found", message="no route"
    )
    client = await _connected(api)

    with pytest.raises(ReadRejectedError, match="no route") as raised:
        await client.status()
    assert type(raised.value) is ReadRejectedError
    await client.close()


# --- downloads -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_link_the_daemon_refuses_is_reported() -> None:
    """The bulk envelope answers 2xx even when the one item inside it failed."""
    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/downloads")] = lambda _: httpx.Response(
        207,
        json={
            "results": [
                {
                    "id": "ed2k://x",
                    "ok": False,
                    "error": {"code": "amuled_rejected", "message": "malformed"},
                }
            ]
        },
    )
    client = await _connected(api)

    with pytest.raises(DownloadRejectedError, match="malformed") as raised:
        await client.start(DownloadRequest(file=_KEY, filename="x", size_bytes=1))
    assert type(raised.value) is DownloadRejectedError


@pytest.mark.asyncio
async def test_a_bulk_envelope_without_an_outcome_is_reported() -> None:
    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/downloads")] = lambda _: httpx.Response(202, json={})
    client = await _connected(api)

    with pytest.raises(DownloadRejectedError):
        await client.start(DownloadRequest(file=_KEY, filename="x", size_bytes=1))


@pytest.mark.asyncio
async def test_downloads_drops_an_entry_with_no_usable_hash() -> None:
    api = FakeAmuleApi(downloads=[{"size_bytes": 10}, {"hash": _HASH}])
    client = await _connected(api)

    downloads = await client.downloads()
    await client.close()

    assert [download.file for download in downloads] == [_KEY]


@pytest.mark.asyncio
async def test_downloads_pages_the_shared_files_past_the_first_hundred() -> None:
    """§7.5: the newest shared file is the one we wait for, and it is the one that falls out."""
    rows = [{"hash": f"{index:032x}", "name": f"{index}.avi"} for index in range(501)]
    api = FakeAmuleApi(shared=rows)
    client = await _connected(api)

    shared = await client.downloads()
    await client.close()

    assert len(shared) == 501
    assert shared[-1].file.native_id == f"{500:032x}"
    # Keyset paging, never offset: a row removed mid-sweep must not shift the window (§7.5).
    sweep = _paths(api, "/api/v1/shared")
    assert all(url.params.get("offset") is None for url in sweep)
    assert sweep[-1].params.get("after") == f"{499:032x}"


@pytest.mark.asyncio
async def test_downloads_asks_pages_of_the_size_it_was_given() -> None:
    rows = [{"hash": f"{index:032x}", "name": f"{index}.avi"} for index in range(5)]
    api = FakeAmuleApi(shared=rows)
    client = await _connected(api, page_size=2)

    shared = await client.downloads()
    await client.close()

    assert len(shared) == 5
    sweep = _paths(api, "/api/v1/shared")
    assert [url.params.get("limit") for url in sweep] == ["2", "2", "2"]


@pytest.mark.asyncio
async def test_a_page_whose_last_row_has_no_anchor_stops_the_sweep() -> None:
    rows: list[dict[str, object]] = [{"hash": f"{index:032x}"} for index in range(500)]
    rows[-1] = {"name": "anchorless"}
    api = FakeAmuleApi(shared=rows)
    client = await _connected(api)

    shared = await client.downloads()
    await client.close()

    assert len(shared) == 499


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/downloads", "/api/v1/shared"])
async def test_a_list_the_daemon_refuses_is_a_refused_read(path: str) -> None:
    api = FakeAmuleApi()
    api.overrides[("GET", path)] = lambda _: error(500, code="amuled_rejected", message="busy")
    client = await _connected(api)

    with pytest.raises(ReadRejectedError, match="busy") as raised:
        await client.downloads()
    assert type(raised.value) is ReadRejectedError
    await client.close()


@pytest.mark.asyncio
async def test_a_list_without_its_envelope_is_unreachable_not_empty() -> None:
    # Read as empty, it would restart every download it hides (stage 2, D13).
    api = FakeAmuleApi()
    api.overrides[("GET", "/api/v1/shared")] = lambda _: httpx.Response(200, json={"shared": 7})
    client = await _connected(api)

    with pytest.raises(ApiUnreachableError, match="/shared"):
        await client.downloads()
    await client.close()


@pytest.mark.asyncio
async def test_start_refuses_a_file_of_another_network_without_asking() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)
    other = FileKey(network=cast(Network, "soulseek"), native_id="Keroro/095.avi")

    with pytest.raises(DownloadRejectedError, match="soulseek"):
        await client.start(DownloadRequest(file=other, filename="095.avi", size_bytes=10))
    await client.close()

    assert api.added_links == []


@pytest.mark.asyncio
async def test_start_queues_the_files_ed2k_link() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)
    download_client: DownloadClient = client

    await download_client.start(
        DownloadRequest(file=_KEY, filename="Keroro 095.avi", size_bytes=10)
    )
    await client.close()

    assert api.added_links == [f"ed2k://|file|Keroro%20095.avi|10|{_HASH}|/"]


@pytest.mark.asyncio
async def test_a_start_the_daemon_refuses_rejects_the_download() -> None:
    api = FakeAmuleApi()
    api.overrides[("POST", "/api/v1/downloads")] = lambda _: httpx.Response(
        207, json={"results": [{"id": "ed2k://x", "ok": False}]}
    )
    client = await _connected(api)

    with pytest.raises(DownloadRejectedError):
        await client.start(DownloadRequest(file=_KEY, filename="Keroro.095.avi", size_bytes=10))


def _downloading(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "hash": _HASH,
        "size_bytes": 10,
        "completed_bytes": 4,
        "status": "downloading",
        "sources": {"total": 1, "transferring": 1},
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_downloads_reads_the_whole_queue_before_the_shared_files() -> None:
    """Queue first: a file cleared between the two reads is then in /shared, not in neither."""
    api = FakeAmuleApi(downloads=[_downloading()])
    client = await _connected(api)

    downloads = await client.downloads()
    await client.close()

    lists = ("/api/v1/downloads", "/api/v1/shared")
    assert [request.url.path for request in api.requests if request.url.path in lists] == [*lists]
    assert _paths(api, "/api/v1/downloads")[0].params.get("status") == "all"
    assert downloads == (
        DownloadStatus(
            file=_KEY,
            bytes_done=4,
            size_bytes=10,
            completed=False,
            waiting_reason=None,
            failure_reason=None,
        ),
    )


@pytest.mark.asyncio
async def test_a_shared_file_the_queue_no_longer_lists_is_completed() -> None:
    cleared = FileKey(network=Network.ED2K, native_id=f"{1:032x}")
    api = FakeAmuleApi(shared=[{"hash": cleared.native_id, "size_bytes": 10}])
    client = await _connected(api)

    downloads = await client.downloads()
    await client.close()

    assert [(download.file, download.completed) for download in downloads] == [(cleared, True)]


@pytest.mark.asyncio
async def test_a_full_partfile_still_completing_is_not_completed_though_shared() -> None:
    """amuled shares partfiles too: neither the bytes nor /shared say it is verified and moved."""
    api = FakeAmuleApi(
        downloads=[_downloading(completed_bytes=10, status="completing")],
        shared=[{"hash": _HASH, "size_bytes": 10}],
    )
    client = await _connected(api)

    downloads = await client.downloads()
    await client.close()

    assert [(download.file, download.completed) for download in downloads] == [(_KEY, False)]


@pytest.mark.asyncio
async def test_downloads_drops_the_rows_without_a_usable_hash() -> None:
    api = FakeAmuleApi(downloads=[{"status": "completed"}], shared=[{"size_bytes": 10}])
    client = await _connected(api)

    assert await client.downloads() == ()
    await client.close()


def _source(ecid: int, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ecid": ecid,
        "name": f"peer {ecid}",
        "user_hash": f"{ecid:032x}",
        "role": "downloading_from",
        "a4af": False,
        "download_state": "queued",
        "downloaded_bytes_session": 0,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_sources_pages_every_client_of_the_download_past_the_first_hundred() -> None:
    """Every list route returns 100 rows when `limit` is omitted (stage 4 spec, D7)."""
    api = FakeAmuleApi(clients={_HASH: [_source(ecid) for ecid in range(1, 601)]})
    client = await _connected(api)
    port: SourceClient = client

    readings = await port.sources(_KEY)
    await client.close()

    assert len(readings) == 600
    assert readings[-1].source_name == "peer 600"
    # Keyset paging on the route's identity column, which is an integer here.
    sweep = _paths(api, f"/api/v1/downloads/{_HASH}/clients")
    assert [url.params.get("sort") for url in sweep] == ["ecid", "ecid"]
    assert all(url.params.get("offset") is None for url in sweep)
    assert sweep[-1].params.get("after") == "500"


@pytest.mark.asyncio
async def test_sources_ask_the_detail_of_only_the_rows_that_offer_us_the_file() -> None:
    rows = [
        _source(1),
        _source(2, role="uploading_to"),
        _source(3, role="none", a4af=True),
    ]
    server = {"ed2k_user_id": 4242, "high_id": False, "server_ip": "176.103.48.36"}
    api = FakeAmuleApi(clients={_HASH: rows}, details={1: {**server, "server_port": 4184}})
    client = await _connected(api)

    readings = await client.sources(_KEY)
    await client.close()

    assert [
        (reading.source_name, reading.role, reading.contact_point, reading.connectable)
        for reading in readings
    ] == [
        (
            "peer 1",
            SourceRole.QUEUED,
            ContactPoint(network=Network.ED2K, server="176.103.48.36:4184"),
            False,
        ),
        ("peer 3", SourceRole.STANDBY, None, None),
    ]
    asked = [r.url.path for r in api.requests if r.url.path.startswith("/api/v1/clients/")]
    assert asked == ["/api/v1/clients/1", "/api/v1/clients/3"]


@pytest.mark.asyncio
async def test_a_client_gone_between_the_list_and_its_detail_is_dropped() -> None:
    """D7: a `404` on the detail drops that row only."""
    api = FakeAmuleApi(clients={_HASH: [_source(1), _source(2), _source(3)]})
    api.overrides[("GET", "/api/v1/clients/2")] = lambda _: error(
        404, code="not_found", message="no client with that ECID in the current snapshot"
    )
    client = await _connected(api)

    readings = await client.sources(_KEY)
    await client.close()

    assert [reading.source_name for reading in readings] == ["peer 1", "peer 3"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code", "raised"),
    [(503, "ec_unavailable", ClientUnreachableError), (500, "amuled_rejected", ReadRejectedError)],
)
async def test_any_other_failure_of_a_detail_fails_the_read(
    status: int, code: str, raised: type[Exception]
) -> None:
    api = FakeAmuleApi(clients={_HASH: [_source(1)]})
    api.overrides[("GET", "/api/v1/clients/1")] = lambda _: error(status, code=code)
    client = await _connected(api)

    with pytest.raises(raised):
        await client.sources(_KEY)
    await client.close()


@pytest.mark.asyncio
async def test_two_rows_of_one_source_read_as_one() -> None:
    """D7: a user hash is not unique among a client's simultaneous connections."""
    rows = [_source(1, user_hash="1f" * 16), _source(2, user_hash="1f" * 16)]
    api = FakeAmuleApi(clients={_HASH: rows})
    client = await _connected(api)

    readings = await client.sources(_KEY)
    await client.close()

    assert [reading.source_name for reading in readings] == ["peer 1"]


@pytest.mark.asyncio
async def test_a_download_that_left_has_no_source() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)

    assert await client.sources(_KEY) == ()
    await client.close()

    assert len(_paths(api, f"/api/v1/downloads/{_HASH}/clients")) == 1


@pytest.mark.asyncio
async def test_a_refusal_other_than_a_missing_download_still_fails_the_read() -> None:
    """`not_found` and `amuled_rejected` map to one class: the read tells them apart."""
    api = FakeAmuleApi(clients={_HASH: []})
    api.overrides[("GET", f"/api/v1/downloads/{_HASH}/clients")] = lambda _: error(
        500, code="amuled_rejected"
    )
    client = await _connected(api)

    with pytest.raises(ReadRejectedError) as raised:
        await client.sources(_KEY)
    assert type(raised.value) is ReadRejectedError
    await client.close()


@pytest.mark.asyncio
async def test_sources_of_a_file_of_another_network_are_none_without_asking() -> None:
    api = FakeAmuleApi()
    client = await _connected(api)

    assert (
        await client.sources(FileKey(network=cast(Network, "soulseek"), native_id="Keroro/095.avi"))
        == ()
    )
    await client.close()

    assert [request.url.path for request in api.requests if "clients" in request.url.path] == []
