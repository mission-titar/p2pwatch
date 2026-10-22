"""A fake amuleapi served through ``httpx.MockTransport``, or on a loopback socket by
``FakeAmuleApiServer``, so the tests drive the real stack.

Its list routes default ``limit`` to 100 like the real ones, which is what makes a client that
forgets to ask for more fail here instead of on a node with a hundred shared files.
"""

import json
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx

from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from tests.fakes.adapters.driven.fake_time import FakeTime

PASSWORD = "s3cret"


TOKEN = "eyJhbGciOi.fake.token"


# The real server's default page size. Unasked-for, it is what a forgetful client receives.
DEFAULT_LIMIT = 100


_SEARCH_ROUTE = re.compile(r"^/api/v1/search/(\d+)/")


_CLIENTS_ROUTE = re.compile(r"^/api/v1/downloads/([^/]+)/clients$")


_CLIENT_ROUTE = re.compile(r"^/api/v1/clients/(\d+)$")


# The keys a per-file client row adds to the client object, absent from its detail.
_FILE_RELATION_KEYS = ("role", "a4af")


def error(status: int, code: str, message: str = "nope", **headers: str) -> httpx.Response:
    """A response in the surface's error envelope."""
    return httpx.Response(
        status, json={"error": {"code": code, "message": message}}, headers=headers
    )


class FakeAmuleApi:
    """Routes the handful of endpoints the adapter uses; any other route raises ``KeyError``."""

    def __init__(
        self,
        *,
        password: str = PASSWORD,
        results: list[dict[str, Any]] | None = None,
        downloads: list[dict[str, Any]] | None = None,
        shared: list[dict[str, Any]] | None = None,
        clients: dict[str, list[dict[str, Any]]] | None = None,
        details: dict[int, dict[str, Any]] | None = None,
        status: dict[str, Any] | None = None,
        version: dict[str, Any] | None = None,
        progress: dict[str, Any] | None = None,
        search_seconds: dict[str, float] | None = None,
        monotonic_clock: MonotonicClock | None = None,
    ) -> None:
        self.password = password
        self.results = results if results is not None else []
        self.downloads = downloads if downloads is not None else []
        self.shared = shared if shared is not None else []
        # Download hash -> its client rows; a hash missing here is a download that left.
        self.clients = clients if clients is not None else {}
        # Ecid -> its detail-only fields, over the client object of its rows.
        self.details = details if details is not None else {}
        self.status = (
            status if status is not None else {"ec_connected": True, "ed2k": {}, "kad": {}}
        )
        self.version = version if version is not None else {"daemon_version": "3.0.1"}
        self.progress = progress if progress is not None else {"state": "finished", "percent": 100}
        # Per query: a search reports `running` that long after its start, then `finished`.
        self.search_seconds = search_seconds if search_seconds is not None else {}
        self.search_started_at: MonotonicInstant | None = None
        # Search id -> (start, query). Ids count up from 42, so a lone search is still 42.
        self.searches: dict[int, tuple[MonotonicInstant, str]] = {}
        self.monotonic_clock = monotonic_clock or FakeTime().monotonic
        self.requests: list[httpx.Request] = []
        self.calls: list[tuple[MonotonicInstant, httpx.Request]] = []
        self.logins = 0
        self.logouts = 0
        self.added_links: list[str] = []
        # Per-route overrides: a callable wins over the default behaviour, once per call.
        self.overrides: dict[tuple[str, str], Callable[[httpx.Request], httpx.Response]] = {}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.calls.append((self.monotonic_clock.now(), request))
        route = (request.method, request.url.path)
        override = self.overrides.get(route)
        if override is not None:
            return override(request)
        path = _SEARCH_ROUTE.sub("/api/v1/search/{id}/", route[1])
        path = _CLIENTS_ROUTE.sub("/api/v1/downloads/{hash}/clients", path)
        handler = _ROUTES[(request.method, _CLIENT_ROUTE.sub("/api/v1/clients/{ecid}", path))]
        unauthenticated = route[1] in ("/api/v1/auth/login", "/api/v1/health")
        assert unauthenticated or request.headers.get("Authorization") == f"Bearer {TOKEN}", (
            f"{route}: missing or stale bearer token"
        )
        return handler(self, request)

    # --- routes ---------------------------------------------------------------------------

    def _login(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body.get("password") != self.password:
            return error(401, "invalid_credentials", "no role matched")
        assert request.url.params.get("include_token") == "true", "login without include_token"
        self.logins += 1
        return httpx.Response(
            200, json={"role": "admin", "expires_at": 0, "session_id": "s", "token": TOKEN}
        )

    def _logout(self, request: httpx.Request) -> httpx.Response:
        self.logouts += 1
        return httpx.Response(204)

    def _start_search(self, request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content).get("query")
        search_id = 42 + len(self.searches)
        self.search_started_at = self.monotonic_clock.now()
        self.searches[search_id] = (self.search_started_at, query)
        return httpx.Response(202, json={"search_id": search_id, "query": query})

    def _search_results(self, request: httpx.Request) -> httpx.Response:
        search_id = _search_id(request)
        window = _page(request, self.results)
        return httpx.Response(
            200,
            json={"results": window, "search_id": search_id, "progress": self._progress(search_id)},
        )

    def _progress(self, search_id: int) -> dict[str, Any]:
        started_at, query = self.searches[search_id]
        seconds = self.search_seconds.get(query)
        if seconds is None:
            return self.progress
        ends_at = started_at + timedelta(seconds=seconds)
        return {"state": "running" if self.monotonic_clock.now() < ends_at else "finished"}

    def _more_search(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(202)

    def _get_status(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self.status)

    def _get_version(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self.version)

    def _add_links(self, request: httpx.Request) -> httpx.Response:
        links = json.loads(request.content)["links"]
        self.added_links.extend(links)
        return httpx.Response(202, json={"results": [{"id": link, "ok": True} for link in links]})

    def _get_downloads(self, request: httpx.Request) -> httpx.Response:
        window = _page(request, self.downloads)
        return httpx.Response(200, json={"downloads": window, "total": len(self.downloads)})

    def _get_shared(self, request: httpx.Request) -> httpx.Response:
        window = _page(request, self.shared)
        return httpx.Response(200, json={"shared": window, "total": len(self.shared)})

    def _get_clients(self, request: httpx.Request) -> httpx.Response:
        match = _CLIENTS_ROUTE.match(request.url.path)
        assert match is not None
        rows = self.clients.get(match.group(1))
        if rows is None:
            return error(404, "not_found", "no download with that hash")
        window = _page(request, rows, identity="ecid")
        return httpx.Response(200, json={"clients": window, "total": len(rows)})

    def _get_client(self, request: httpx.Request) -> httpx.Response:
        match = _CLIENT_ROUTE.match(request.url.path)
        assert match is not None
        ecid = int(match.group(1))
        rows = [row for listed in self.clients.values() for row in listed if row["ecid"] == ecid]
        client = {key: field for key, field in rows[0].items() if key not in _FILE_RELATION_KEYS}
        return httpx.Response(200, json={**client, **self.details.get(ecid, {})})


def _search_id(request: httpx.Request) -> int:
    match = _SEARCH_ROUTE.match(request.url.path)
    assert match is not None
    return int(match.group(1))


def _page(
    request: httpx.Request, rows: list[dict[str, Any]], *, identity: str = "hash"
) -> list[dict[str, Any]]:
    """Keyset paging on the route's identity column, with the surface's own 100-row default for
    ``limit``. The rows are given in that column's order; ``ecid`` compares as a number."""
    params = request.url.params
    after = params.get("after")
    window = rows
    if after is not None and identity == "ecid":
        window = [row for row in rows if int(row["ecid"]) > int(after)]
    elif after is not None:
        window = [row for row in rows if str(row.get(identity, "")) > after]
    limit = int(params.get("limit", DEFAULT_LIMIT))
    return window[:limit]


_ROUTES: dict[tuple[str, str], Callable[[FakeAmuleApi, httpx.Request], httpx.Response]] = {
    ("POST", "/api/v1/auth/login"): FakeAmuleApi._login,
    ("POST", "/api/v1/auth/logout"): FakeAmuleApi._logout,
    ("POST", "/api/v1/search"): FakeAmuleApi._start_search,
    ("GET", "/api/v1/search/{id}/results"): FakeAmuleApi._search_results,
    ("POST", "/api/v1/search/{id}/more"): FakeAmuleApi._more_search,
    ("GET", "/api/v1/status"): FakeAmuleApi._get_status,
    ("GET", "/api/v1/version"): FakeAmuleApi._get_version,
    ("POST", "/api/v1/downloads"): FakeAmuleApi._add_links,
    ("GET", "/api/v1/downloads"): FakeAmuleApi._get_downloads,
    ("GET", "/api/v1/shared"): FakeAmuleApi._get_shared,
    ("GET", "/api/v1/downloads/{hash}/clients"): FakeAmuleApi._get_clients,
    ("GET", "/api/v1/clients/{ecid}"): FakeAmuleApi._get_client,
}
