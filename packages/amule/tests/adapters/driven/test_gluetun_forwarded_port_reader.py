"""GluetunForwardedPortReader: gluetun's port when it reports one, None on any failure."""

import socket
from collections.abc import Iterator

import pytest

from p2pwatch_amule.adapters.driven.gluetun_forwarded_port_reader import (
    GluetunForwardedPortReader,
)
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.fake_gluetun_control_server import FakeGluetunControlServer


@pytest.fixture
def gluetun() -> Iterator[FakeGluetunControlServer]:
    with FakeGluetunControlServer() as gluetun:
        yield gluetun


def reader(
    gluetun: FakeGluetunControlServer, logger: FakeLogger, control_url: str | None = None
) -> GluetunForwardedPortReader:
    return GluetunForwardedPortReader(
        control_url=control_url or gluetun.control_url,
        timeout_seconds=0.2,
        logger=logger,
        url_opener=gluetun.url_opener,
    )


def test_the_forwarded_port_is_read_from_gluetuns_control_server(
    gluetun: FakeGluetunControlServer,
) -> None:
    logger = FakeLogger()
    assert reader(gluetun, logger, gluetun.control_url + "/").read_forwarded_port() == 51820
    assert gluetun.request_lines == ["GET /v1/portforward HTTP/1.1"]
    assert logger.lines == []


@pytest.mark.parametrize(
    "body",
    [
        b'{"port": 0}',
        b'{"port": -1}',
        b'{"port": 65536}',
        b'{"port": "51820"}',
        b'{"port": 51820.0}',
        b'{"port": true}',
        b'{"other": 1}',
        b"[1, 2, 3]",
        b"<html>nope</html>",
        b"\xff\xfe",
    ],
)
def test_a_reply_without_a_positive_integer_port_is_no_port(
    gluetun: FakeGluetunControlServer, body: bytes
) -> None:
    gluetun.body = body
    logger = FakeLogger()
    assert reader(gluetun, logger).read_forwarded_port() is None
    assert logger.lines == [LoggedLine("warning", f"gluetun reports no forwarded port ({body!r})")]


def test_a_reply_is_logged_up_to_its_first_100_bytes(gluetun: FakeGluetunControlServer) -> None:
    gluetun.body = b"x" * 101
    logger = FakeLogger()
    assert reader(gluetun, logger).read_forwarded_port() is None
    assert logger.lines == [
        LoggedLine("warning", f"gluetun reports no forwarded port ({b'x' * 100!r})")
    ]


@pytest.mark.parametrize(
    ("status", "raw_reply", "is_holding", "error"),
    [
        (500, None, False, "HTTP Error 500: Internal Server Error"),
        (200, b"garbage\r\n", False, "garbage"),
        (200, b"", False, "Remote end closed connection without response"),
        (200, None, True, "timed out"),
    ],
)
def test_a_failed_request_is_no_port(
    gluetun: FakeGluetunControlServer,
    status: int,
    raw_reply: bytes | None,
    is_holding: bool,
    error: str,
) -> None:
    gluetun.status, gluetun.raw_reply, gluetun.is_holding = status, raw_reply, is_holding
    logger = FakeLogger()
    assert reader(gluetun, logger).read_forwarded_port() is None
    assert [line.level for line in logger.lines] == ["warning"]
    assert logger.lines[0].message.startswith("gluetun's control server is unavailable (")
    assert error in logger.lines[0].message


def test_a_refused_connection_is_no_port(gluetun: FakeGluetunControlServer) -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    logger = FakeLogger()
    assert reader(gluetun, logger, f"http://127.0.0.1:{port}").read_forwarded_port() is None
    assert [line.level for line in logger.lines] == ["warning"]
    assert logger.lines[0].message.startswith("gluetun's control server is unavailable (<urlopen")
    assert "Connection refused" in logger.lines[0].message
