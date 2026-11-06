"""AmuleApiListenPortClient: a login, then a PATCH of both ports; any refusal a ListenPortError."""

import json
import re
import socket
from collections.abc import Iterator

import pytest

from p2pwatch_amule.adapters.driven.amule_api_listen_port_client import AmuleApiListenPortClient
from p2pwatch_amule.domain.listen_port_error import ListenPortError
from tests.fakes.fake_amule_api_server import TOKEN, FakeAmuleApiServer

LOGIN = "POST /api/v1/auth/login?include_token=true HTTP/1.1"
PATCH = "PATCH /api/v1/preferences HTTP/1.1"


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


def test_each_call_logs_in_again(amule_api: FakeAmuleApiServer) -> None:
    client = listen_port_client(amule_api)

    client.set_listen_port(40123)
    client.set_listen_port(40124)

    assert amule_api.request_lines == [LOGIN, PATCH, LOGIN, PATCH]


def test_a_refused_password_patches_nothing(amule_api: FakeAmuleApiServer) -> None:
    message = 'POST /api/v1/auth/login?include_token=true: 401 b\'{"error":{"code":"invalid_cr'

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}"):
        listen_port_client(amule_api, api_password="wrong").set_listen_port(40123)

    assert amule_api.request_lines == [LOGIN]


@pytest.mark.parametrize(
    "login_body", [b"{}", b'{"token": ""}', b'{"token": 1}', b"[]", b"<html>", b"\xff\xfe"]
)
def test_a_login_without_a_token_patches_nothing(
    *, amule_api: FakeAmuleApiServer, login_body: bytes
) -> None:
    amule_api.login_body = login_body
    message = f"amuleapi's login answered without a token ({login_body!r})"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$"):
        listen_port_client(amule_api).set_listen_port(40123)

    assert amule_api.request_lines == [LOGIN]


def test_a_token_amuleapi_refuses_is_an_error(amule_api: FakeAmuleApiServer) -> None:
    amule_api.login_body = b'{"token": "revoked"}'

    with pytest.raises(ListenPortError, match="^PATCH /api/v1/preferences: 401 "):
        listen_port_client(amule_api).set_listen_port(40123)


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (400, b'{"error":{"code":"amuled_rejected","message":"Could not rebind"}}'),
        (400, b'{"error":{"code":"bad_request","message":"tcp_port out of range (1-65532)"}}'),
        (503, b'{"error":{"code":"ec_unavailable"}}'),
        (500, b"x" * 101),
    ],
)
def test_a_refused_patch_is_an_error_carrying_its_reply_s_first_100_bytes(
    *, amule_api: FakeAmuleApiServer, status: int, body: bytes
) -> None:
    amule_api.preferences_status, amule_api.preferences_body = status, body
    message = f"PATCH /api/v1/preferences: {status} {body[:100]!r}"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$"):
        listen_port_client(amule_api).set_listen_port(40123)


def test_a_refusal_whose_body_breaks_off_is_an_error_without_it(
    amule_api: FakeAmuleApiServer,
) -> None:
    amule_api.raw_reply = b"HTTP/1.1 400 Bad Request\r\nTransfer-Encoding: chunked\r\n\r\nzz\r\n"
    message = "POST /api/v1/auth/login?include_token=true: 400 b''"

    with pytest.raises(ListenPortError, match=f"^{re.escape(message)}$"):
        listen_port_client(amule_api).set_listen_port(40123)


@pytest.mark.parametrize(
    ("raw_reply", "is_holding", "error"),
    [
        (b"garbage\r\n", False, "garbage"),
        (b"", False, "Remote end closed connection without response"),
        (None, True, "timed out"),
    ],
)
def test_a_failed_request_is_an_error(
    *,
    amule_api: FakeAmuleApiServer,
    raw_reply: bytes | None,
    is_holding: bool,
    error: str,
) -> None:
    amule_api.raw_reply, amule_api.is_holding = raw_reply, is_holding

    with pytest.raises(ListenPortError, match="^POST /api/v1/auth/login") as raised:
        listen_port_client(amule_api).set_listen_port(40123)

    assert error in str(raised.value)


def test_a_refused_connection_is_an_error(amule_api: FakeAmuleApiServer) -> None:
    # amuleapi's starting state: it listens only once its EC login succeeded.
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    client = listen_port_client(amule_api, api_url=f"http://127.0.0.1:{port}")

    with pytest.raises(ListenPortError, match="Connection refused"):
        client.set_listen_port(40123)
