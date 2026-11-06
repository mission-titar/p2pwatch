import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Any, Protocol, Self
from urllib.request import ProxyHandler, build_opener

READY_BODY = b'{"status":"ok","ec_connected":true,"snapshot_ready":true}'
TOKEN = "token-of-the-fake"
_UNAUTHORIZED_BODY = b'{"error":{"code":"unauthorized","message":"invalid or expired token"}}'
_INVALID_CREDENTIALS_BODY = b'{"error":{"code":"invalid_credentials","message":"bad password"}}'


@dataclass(kw_only=True, frozen=True)
class ApiRequest:
    line: str
    authorization: str | None
    body: bytes


class Route(Protocol):
    def __call__(self, request: ApiRequest) -> tuple[int, bytes]: ...


class FakeAmuleApiServer:
    """amuleapi on a loopback port: GET answers ``health_status`` and ``health_body``, POST logs in
    with ``password`` for ``login_body``, PATCH answers ``preferences_status`` and
    ``preferences_body`` to ``TOKEN``'s bearer; ``raw_reply``'s bytes, or no answer while
    ``is_holding``, replace any; records each request."""

    def __init__(self, *, port: int = 0) -> None:
        self.health_status = 200
        self.health_body = READY_BODY
        self.password = "s3cret"
        self.login_body = json.dumps({"token": TOKEN, "role": "admin"}).encode()
        self.preferences_status = 200
        self.preferences_body = b'{"connection":{"tcp_port":40123,"udp_port":40123}}'
        self.raw_reply: bytes | None = None
        self.is_holding = False
        self.requests: list[ApiRequest] = []
        self._released = Event()
        fake_server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self._answer(lambda request: (fake_server.health_status, fake_server.health_body))

            def do_POST(self) -> None:
                self._answer(fake_server._login)

            def do_PATCH(self) -> None:
                self._answer(fake_server._set_preferences)

            def _answer(self, route: Route) -> None:
                request = ApiRequest(
                    line=self.requestline,
                    authorization=self.headers.get("Authorization"),
                    body=self.rfile.read(int(self.headers.get("Content-Length", 0))),
                )
                fake_server.requests.append(request)
                if fake_server.is_holding:
                    fake_server._released.wait()
                    return
                if fake_server.raw_reply is not None:
                    self.wfile.write(fake_server.raw_reply)
                    return
                status, body = route(request)
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                """Silent: the requests are recorded instead."""

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        host, bound_port = self._server.server_address[:2]
        self.api_url = f"http://{host!s}:{bound_port}"
        self.url_opener = build_opener(ProxyHandler({}))  # direct, whatever HTTP_PROXY says
        # Polled every 10 ms, not 0.5 s: shutdown waits for the next poll.
        self._thread = Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01})

    @property
    def request_lines(self) -> list[str]:
        return [request.line for request in self.requests]

    def _login(self, request: ApiRequest) -> tuple[int, bytes]:
        if json.loads(request.body).get("password") != self.password:
            return 401, _INVALID_CREDENTIALS_BODY
        return 200, self.login_body

    def _set_preferences(self, request: ApiRequest) -> tuple[int, bytes]:
        if request.authorization != f"Bearer {TOKEN}":
            return 401, _UNAUTHORIZED_BODY
        return self.preferences_status, self.preferences_body

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._released.set()
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()
