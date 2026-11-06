"""AmuleApiHealthClient: ready on a 200 with ec_connected true, not ready on anything else."""

import logging
import socket
from collections.abc import Iterator

import pytest

from p2pwatch_amule.adapters.driven.amule_api_health_client import AmuleApiHealthClient
from tests.fakes.fake_amule_api_server import FakeAmuleApiServer

# The module's name, which an operator's filters read.
LOGGER_NAME = "p2pwatch_amule.adapters.driven.amule_api_health_client"


@pytest.fixture
def amule_api() -> Iterator[FakeAmuleApiServer]:
    with FakeAmuleApiServer() as amule_api:
        yield amule_api


def health_client(
    amule_api: FakeAmuleApiServer, *, api_url: str | None = None
) -> AmuleApiHealthClient:
    return AmuleApiHealthClient(
        api_url=api_url or amule_api.api_url,
        timeout_seconds=0.2,
        url_opener=amule_api.url_opener,
    )


def _logged_lines(caplog: pytest.LogCaptureFixture) -> list[tuple[str, int, str]]:
    return [(record.name, record.levelno, record.getMessage()) for record in caplog.records]


@pytest.mark.parametrize(
    "body",
    [
        b'{"status":"ok","ec_connected":true,"snapshot_ready":true}',
        # snapshot_ready is not read: ec_connected alone says amuleapi is linked to amuled.
        b'{"status":"ok","ec_connected":true,"snapshot_ready":false}',
    ],
)
def test_a_200_with_ec_connected_true_is_ready_and_logs_nothing(
    *, amule_api: FakeAmuleApiServer, body: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    amule_api.health_body = body

    assert health_client(amule_api, api_url=amule_api.api_url + "/").is_api_ready() is True

    assert amule_api.request_lines == ["GET /api/v1/health HTTP/1.1"]
    assert _logged_lines(caplog) == []


@pytest.mark.parametrize(
    "body",
    [
        b'{"status":"ok","ec_connected":false,"snapshot_ready":true}',
        b'{"status":"ok","ec_connected":"true"}',
        b'{"status":"ok","ec_connected":1}',
        b'{"status":"ok"}',
        b"[true]",
        b"<html>nope</html>",
        b"\xff\xfe",
    ],
)
def test_a_200_without_ec_connected_true_is_not_ready_logged_under_the_module_s_name(
    *, amule_api: FakeAmuleApiServer, body: bytes, caplog: pytest.LogCaptureFixture
) -> None:
    amule_api.health_body = body

    assert health_client(amule_api).is_api_ready() is False

    assert _logged_lines(caplog) == [
        (LOGGER_NAME, logging.WARNING, f"amuleapi reports no link to amuled (200 {body!r})")
    ]


def test_a_success_other_than_200_is_not_ready(
    *, amule_api: FakeAmuleApiServer, caplog: pytest.LogCaptureFixture
) -> None:
    amule_api.health_status = 202

    assert health_client(amule_api).is_api_ready() is False

    assert _logged_lines(caplog) == [
        (
            LOGGER_NAME,
            logging.WARNING,
            f"amuleapi reports no link to amuled (202 {amule_api.health_body!r})",
        )
    ]


def test_a_reply_is_logged_up_to_its_first_100_bytes(
    *, amule_api: FakeAmuleApiServer, caplog: pytest.LogCaptureFixture
) -> None:
    amule_api.health_body = b"x" * 101

    assert health_client(amule_api).is_api_ready() is False

    assert _logged_lines(caplog) == [
        (LOGGER_NAME, logging.WARNING, f"amuleapi reports no link to amuled (200 {b'x' * 100!r})")
    ]


@pytest.mark.parametrize(
    ("status", "raw_reply", "is_holding", "error"),
    [
        (503, None, False, "HTTP Error 503: Service Unavailable"),
        (200, b"garbage\r\n", False, "garbage"),
        (200, b"", False, "Remote end closed connection without response"),
        (200, None, True, "timed out"),
    ],
)
def test_a_failed_request_is_not_ready_logged_under_the_module_s_name(
    *,
    amule_api: FakeAmuleApiServer,
    status: int,
    raw_reply: bytes | None,
    is_holding: bool,
    error: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    amule_api.health_status, amule_api.raw_reply, amule_api.is_holding = (
        status,
        raw_reply,
        is_holding,
    )

    assert health_client(amule_api).is_api_ready() is False

    [(name, level, message)] = _logged_lines(caplog)
    assert (name, level) == (LOGGER_NAME, logging.WARNING)
    assert message.startswith("amuleapi is unavailable (")
    assert error in message


def test_a_refused_connection_is_not_ready(
    *, amule_api: FakeAmuleApiServer, caplog: pytest.LogCaptureFixture
) -> None:
    # amuleapi's normal starting state: it listens only once its EC login succeeded.
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]

    assert health_client(amule_api, api_url=f"http://127.0.0.1:{port}").is_api_ready() is False

    [(name, level, message)] = _logged_lines(caplog)
    assert (name, level) == (LOGGER_NAME, logging.WARNING)
    assert message.startswith("amuleapi is unavailable (<urlopen")
    assert "Connection refused" in message
