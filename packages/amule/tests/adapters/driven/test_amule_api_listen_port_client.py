"""AmuleApiListenPortClient: the TCP port read, both ports patched, under a kept token; its
failures in three."""

import json
import re
import socket
from collections.abc import Iterator

import pytest

from p2pwatch_amule.adapters.driven.amule_api_listen_port_client import AmuleApiListenPortClient
from p2pwatch_amule.domain.listen_port_error import (
    ApiNotReadyError,
    ListenPortError,
    ListenPortRejectedError,
)
from tests.fakes.fake_amule_api_server import TOKEN, FakeAmuleApiServer

LOGIN = "POST /api/v1/auth/login?include_token=true HTTP/1.1"
PATCH = "PATCH /api/v1/preferences HTTP/1.1"
GET = "GET /api/v1/preferences HTTP/1.1"


@pytest.fixture
def amule_api() -> Iterator[FakeAmuleApiServer]:
    with FakeAmuleApiServer() as amule_api:
        yield amule_api


def listen_port_client(
    amule_api: FakeAmuleApiServer, *, api_url: str | None = None, api_password: str = "s3cret"
) -> AmuleApiListenPortClient:
    return AmuleApiListenPortClient(
        api_url=api_url or amule_api.api_url,
        api_password=api_password,
        timeout_seconds=0.2,
        url_opener=amule_api.url_opener,
    )


def test_the_ports_are_patched_with_the_token_of_a_login(amule_api: FakeAmuleApiServer) -> None:
    listen_port_client(amule_api, api_url=amule_api.api_url + "/").set_listen_port(40123)

    login, patch = amule_api.requests
    assert (login.line, login.authorization) == (LOGIN, None)
    assert json.loads(login.body) == {"password": "s3cret"}
    assert (patch.line, patch.authorization) == (PATCH, f"Bearer {TOKEN}")
    assert json.loads(patch.body) == {"connection": {"tcp_port": 40123, "udp_port": 40123}}


def test_the_token_is_kept_for_the_next_call(amule_api: FakeAmuleApiServer) -> None:
    client = listen_port_client(amule_api)

    client.set_listen_port(40123)
    client.set_listen_port(40124)

    assert amule_api.request_lines == [LOGIN, PATCH, PATCH]


def test_a_kept_token_refused_logs_in_again_once(amule_api: FakeAmuleApiServer) -> None:
    client = listen_port_client(amule_api)
    client.set_listen_port(40123)
    amule_api.token = "renewed"

    client.set_listen_port(40124)

    assert amule_api.request_lines == [LOGIN, PATCH, PATCH, LOGIN, PATCH]
    assert amule_api.requests[-1].authorization == "Bearer renewed"


def test_a_token_refused_after_the_re_login_is_amuleapi_not_ready(
    amule_api: FakeAmuleApiServer,
) -> None:
    client = listen_port_client(amule_api)
    client.set_listen_port(40123)
    amule_api.token = "renewed"
    amule_api.login_body = b'{"token": "revoked"}'

    with pytest.raises(ApiNotReadyError, match="^PATCH /api/v1/preferences: 401 "):
        client.set_listen_port(40124)

    assert amule_api.request_lines == [LOGIN, PATCH, PATCH, LOGIN, PATCH]


def test_a_refused_password_is_neither_not_ready_nor_a_rejection(
    amule_api: FakeAmuleApiServer,
) -> None:
    message = 'POST /api/v1/auth/login?include_token=true: 401 b\'{"error":{"code":"invalid_cr'

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}") as raised:
        listen_port_client(amule_api, api_password="wrong").set_listen_port(40123)

    assert type(raised.value) is ListenPortError
    assert amule_api.request_lines == [LOGIN]


@pytest.mark.parametrize(
    "login_body", [b"{}", b'{"token": ""}', b'{"token": 1}', b"[]", b"<html>", b"\xff\xfe"]
)
def test_a_login_without_a_token_patches_nothing(
    *, amule_api: FakeAmuleApiServer, login_body: bytes
) -> None:
    amule_api.login_body = login_body
    message = f"amuleapi's login answered without a token ({login_body!r})"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$") as raised:
        listen_port_client(amule_api).set_listen_port(40123)

    assert type(raised.value) is ListenPortError
    assert amule_api.request_lines == [LOGIN]


def test_a_fresh_token_refused_is_amuleapi_not_ready_without_a_second_login(
    amule_api: FakeAmuleApiServer,
) -> None:
    amule_api.login_body = b'{"token": "revoked"}'

    with pytest.raises(ApiNotReadyError, match="^PATCH /api/v1/preferences: 401 "):
        listen_port_client(amule_api).set_listen_port(40123)

    assert amule_api.request_lines == [LOGIN, PATCH]


@pytest.mark.parametrize(
    ("status", "body", "error_class"),
    [
        (
            400,
            b'{"error":{"code":"amuled_rejected","message":"Could not rebind"}}',
            ListenPortRejectedError,
        ),
        (
            400,
            b'{"error":{"code":"bad_request","message":"tcp_port out of range (1-65532)"}}',
            ListenPortRejectedError,
        ),
        (503, b'{"error":{"code":"ec_unavailable"}}', ApiNotReadyError),
        (500, b"x" * 101, ListenPortError),
    ],
)
def test_a_refused_patch_is_an_error_carrying_its_reply_s_first_100_bytes(
    *,
    amule_api: FakeAmuleApiServer,
    status: int,
    body: bytes,
    error_class: type[ListenPortError],
) -> None:
    amule_api.preferences_status, amule_api.preferences_body = status, body
    message = f"PATCH /api/v1/preferences: {status} {body[:100]!r}"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$") as raised:
        listen_port_client(amule_api).set_listen_port(40123)

    assert type(raised.value) is error_class


def test_the_tcp_port_is_read_with_the_kept_token(amule_api: FakeAmuleApiServer) -> None:
    client = listen_port_client(amule_api)

    first_port = client.read_listen_port()
    amule_api.preferences_body = b'{"connection":{"tcp_port":51820,"udp_port":4672}}'

    assert (first_port, client.read_listen_port()) == (40123, 51820)
    assert amule_api.request_lines == [LOGIN, GET, GET]
    assert amule_api.requests[-1].authorization == f"Bearer {TOKEN}"


def test_a_read_whose_kept_token_is_refused_logs_in_again_once(
    amule_api: FakeAmuleApiServer,
) -> None:
    client = listen_port_client(amule_api)
    client.read_listen_port()
    amule_api.token = "renewed"
    amule_api.login_body = b'{"token": "revoked"}'

    with pytest.raises(ApiNotReadyError, match="^GET /api/v1/preferences: 401 "):
        client.read_listen_port()

    assert amule_api.request_lines == [LOGIN, GET, GET, LOGIN, GET]


@pytest.mark.parametrize(
    ("status", "body", "error_class"),
    [
        (503, b'{"error":{"code":"ec_unavailable"}}', ApiNotReadyError),
        (400, b'{"error":{"code":"bad_request"}}', ListenPortError),
        (500, b"x" * 101, ListenPortError),
    ],
)
def test_a_refused_read_is_an_error_carrying_its_reply_s_first_100_bytes(
    *,
    amule_api: FakeAmuleApiServer,
    status: int,
    body: bytes,
    error_class: type[ListenPortError],
) -> None:
    amule_api.preferences_status, amule_api.preferences_body = status, body
    message = f"GET /api/v1/preferences: {status} {body[:100]!r}"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$") as raised:
        listen_port_client(amule_api).read_listen_port()

    assert type(raised.value) is error_class


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b'{"connection": {}}',
        b'{"connection": {"tcp_port": "4662"}}',
        b'{"connection": {"tcp_port": true}}',
        b'{"connection": []}',
        b"[]",
        b"<html>",
        b"\xff\xfe",
    ],
)
def test_preferences_without_a_tcp_port_are_an_error(
    *, amule_api: FakeAmuleApiServer, body: bytes
) -> None:
    amule_api.preferences_body = body
    message = f"amuleapi's preferences answered without a TCP port ({body!r})"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$") as raised:
        listen_port_client(amule_api).read_listen_port()

    assert type(raised.value) is ListenPortError


def test_a_login_amuleapi_cannot_serve_yet_is_amuleapi_not_ready(
    amule_api: FakeAmuleApiServer,
) -> None:
    amule_api.raw_reply = b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n"

    with pytest.raises(
        ApiNotReadyError, match=r"^POST /api/v1/auth/login\?include_token=true: 503"
    ):
        listen_port_client(amule_api).set_listen_port(40123)


def test_a_refusal_whose_body_breaks_off_is_an_error_without_it(
    amule_api: FakeAmuleApiServer,
) -> None:
    amule_api.raw_reply = b"HTTP/1.1 400 Bad Request\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\n"
    message = "POST /api/v1/auth/login?include_token=true: 400 b''"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$"):
        listen_port_client(amule_api).set_listen_port(40123)


@pytest.mark.parametrize(
    ("raw_reply", "error"),
    [(b"garbage\r\n", "garbage"), (b"", "Remote end closed connection without response")],
)
def test_a_failed_request_is_an_error(
    *, amule_api: FakeAmuleApiServer, raw_reply: bytes, error: str
) -> None:
    amule_api.raw_reply = raw_reply

    with pytest.raises(ListenPortError, match="^POST /api/v1/auth/login") as raised:
        listen_port_client(amule_api).set_listen_port(40123)

    assert type(raised.value) is ListenPortError
    assert error in str(raised.value)


def test_a_timeout_is_amuleapi_not_ready(amule_api: FakeAmuleApiServer) -> None:
    # amuleapi serialises its EC calls through one worker: a slow answer is a busy amuleapi.
    amule_api.is_holding = True

    with pytest.raises(ApiNotReadyError, match="^POST /api/v1/auth/login.*timed out"):
        listen_port_client(amule_api).set_listen_port(40123)


def test_a_refused_connection_is_amuleapi_not_ready(amule_api: FakeAmuleApiServer) -> None:
    # amuleapi's starting state: it listens only once its EC login succeeded.
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    client = listen_port_client(amule_api, api_url=f"http://127.0.0.1:{port}")

    with pytest.raises(ApiNotReadyError, match="^POST /api/v1/auth/login.*Connection refused"):
        client.set_listen_port(40123)
