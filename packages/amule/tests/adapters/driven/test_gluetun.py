"""forwarded_port: gluetun's port when it reports one, None on any failure (defensive parse)."""

import http.client
import io
import urllib.error
import urllib.request
from collections.abc import Callable

import pytest

from p2pwatch_amule.adapters.driven.gluetun import forwarded_port
from tests.fakes import FakeLogger

Urlopen = Callable[..., io.BytesIO]


def _replying(body: bytes) -> Urlopen:
    def urlopen(url: str, *, timeout: float) -> io.BytesIO:
        return io.BytesIO(body)

    return urlopen


def _raising(error: Exception) -> Urlopen:
    def urlopen(url: str, *, timeout: float) -> io.BytesIO:
        raise error

    return urlopen


def test_the_forwarded_port_is_read_from_gluetuns_control_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, float]] = []

    def urlopen(url: str, *, timeout: float) -> io.BytesIO:
        requests.append((url, timeout))
        return io.BytesIO(b'{"port": 51820}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    logger = FakeLogger()
    assert forwarded_port("http://gluetun:8000/", logger) == 51820
    assert requests == [("http://gluetun:8000/v1/portforward", 10)]
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
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _replying(body))
    logger = FakeLogger()
    assert forwarded_port("http://gluetun:8000", logger) is None
    assert [(line.level, line.message) for line in logger.lines] == [
        ("warning", f"gluetun reports no forwarded port ({body[:100]!r})")
    ]


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("connection refused"),
        urllib.error.HTTPError("http://gluetun:8000/v1/portforward", 500, "boom", {}, None),  # type: ignore[arg-type]
        TimeoutError("timed out"),
        ConnectionResetError("reset"),
        http.client.BadStatusLine("garbage"),
    ],
)
def test_a_failed_request_is_no_port(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _raising(error))
    logger = FakeLogger()
    assert forwarded_port("http://gluetun:8000", logger) is None
    assert [(line.level, line.message) for line in logger.lines] == [
        ("warning", f"gluetun's control server is unavailable ({error})")
    ]
