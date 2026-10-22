import json
from collections.abc import Mapping
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, Self
from urllib.request import ProxyHandler, build_opener


class FakeGitHubServer:
    """GitHub's REST API on a loopback port: set answers by (request path, Accept), 404 otherwise.

    Records each request's path and headers."""

    def __init__(self) -> None:
        self.answers_by_path_and_accept: dict[tuple[str, str], tuple[int, bytes]] = {}
        self.requests: list[tuple[str, Message]] = []
        fake_server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                fake_server.requests.append((self.path, self.headers))
                accept = self.headers["Accept"]
                status, body = fake_server.answers_by_path_and_accept.get(
                    (self.path, accept), (404, b'{"message": "Not Found"}')
                )
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                """Silent: the requests are recorded instead."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address[:2]
        self.api_url = f"http://{host!s}:{port}"
        self.url_opener = build_opener(ProxyHandler({}))  # direct, whatever HTTP_PROXY says
        self._thread = Thread(target=self._server.serve_forever)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()

    def answer_json(self, path: str, document: Mapping[str, Any]) -> None:
        self.answers_by_path_and_accept[(path, "application/vnd.github+json")] = (
            200,
            json.dumps(document).encode(),
        )

    def answer_raw(self, path: str, status: int, body: bytes) -> None:
        self.answers_by_path_and_accept[(path, "application/vnd.github.raw+json")] = (status, body)
