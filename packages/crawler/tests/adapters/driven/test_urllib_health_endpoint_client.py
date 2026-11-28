"""UrllibHealthEndpointClient: healthy on a 200 within its timeout, unhealthy on anything else."""

import logging
import socket
from collections.abc import Iterator

import pytest

from p2pwatch.adapters.driven.urllib_health_endpoint_client import UrllibHealthEndpointClient
from tests.fakes.fake_health_endpoint_server import FakeHealthEndpointServer

# The module's name, which an operator's filters read.
_LOGGER_NAME = "p2pwatch.adapters.driven.urllib_health_endpoint_client"


@pytest.fixture
def webui() -> Iterator[FakeHealthEndpointServer]:
    with FakeHealthEndpointServer() as webui:
        yield webui


def _client(
    webui: FakeHealthEndpointServer, *, url: str | None = None
) -> UrllibHealthEndpointClient:
    return UrllibHealthEndpointClient(
        url=url or webui.url, timeout_seconds=0.2, url_opener=webui.url_opener
    )


def _logged_lines(caplog: pytest.LogCaptureFixture) -> list[tuple[str, int, str]]:
    return [(record.name, record.levelno, record.getMessage()) for record in caplog.records]


def _warning(caplog: pytest.LogCaptureFixture) -> str:
    """The message of the one line logged, a warning under the module's name."""
    lines = _logged_lines(caplog)
    assert [(name, level) for name, level, _ in lines] == [(_LOGGER_NAME, logging.WARNING)]
    return lines[0][2]


def test_a_200_is_healthy_and_logs_nothing(
    *, webui: FakeHealthEndpointServer, caplog: pytest.LogCaptureFixture
) -> None:
    assert _client(webui).is_node_healthy() is True

    assert webui.request_lines == ["GET /health HTTP/1.1"]
    assert _logged_lines(caplog) == []


@pytest.mark.parametrize("status", [503, 202])
def test_any_other_status_is_unhealthy_logged_under_the_module_s_name(
    *, webui: FakeHealthEndpointServer, status: int, caplog: pytest.LogCaptureFixture
) -> None:
    webui.status = status

    assert _client(webui).is_node_healthy() is False

    assert _logged_lines(caplog) == [
        (_LOGGER_NAME, logging.WARNING, f"the webui answers /health with {status}")
    ]


@pytest.mark.parametrize(
    ("raw_reply", "is_holding", "error"),
    [
        (b"garbage\r\n", False, "garbage"),
        (b"", False, "Remote end closed connection without response"),
        (None, True, "timed out"),
    ],
    ids=["not-http", "closed", "past-the-timeout"],
)
def test_a_reply_short_of_a_status_is_unhealthy_logged_under_the_module_s_name(
    *,
    webui: FakeHealthEndpointServer,
    raw_reply: bytes | None,
    is_holding: bool,
    error: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    webui.raw_reply, webui.is_holding = raw_reply, is_holding

    assert _client(webui).is_node_healthy() is False

    message = _warning(caplog)
    assert message.startswith("the webui does not answer /health (")
    assert error in message


def test_a_refused_connection_is_unhealthy(
    *, webui: FakeHealthEndpointServer, caplog: pytest.LogCaptureFixture
) -> None:
    # The webui's state until the crawler has opened its databases.
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]

    assert _client(webui, url=f"http://127.0.0.1:{port}/health").is_node_healthy() is False

    message = _warning(caplog)
    assert message.startswith("the webui does not answer /health (<urlopen")
    assert "Connection refused" in message
