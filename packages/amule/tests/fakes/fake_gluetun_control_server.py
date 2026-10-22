from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from typing import Any, Self
from urllib.request import ProxyHandler, build_opener


class FakeGluetunControlServer:
    """gluetun's control server on a loopback port: each GET gets ``status`` and ``body``, or
    ``raw_reply``'s bytes, or no answer while ``is_holding``; records each request line."""

    def __init__(self) -> None:
        self.status = 200
        self.body = b'{"port": 51820}'
        self.raw_reply: bytes | None = None
        self.is_holding = False
        self.request_lines: list[str] = []
        self._released = Event()
        fake_server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                # requestline, not path, which http.server strips of a leading //.
                fake_server.request_lines.append(self.requestline)
                if fake_server.is_holding:
                    fake_server._released.wait()
                    return
                if fake_server.raw_reply is not None:
                    self.wfile.write(fake_server.raw_reply)
                    return
                self.send_response(fake_server.status)
                self.send_header("Content-Length", str(len(fake_server.body)))
                self.end_headers()
                self.wfile.write(fake_server.body)

            def log_message(self, format: str, *args: Any) -> None:
                """Silent: the requests are recorded instead."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = self._server.server_address[:2]
        self.control_url = f"http://{host!s}:{port}"
        self.url_opener = build_opener(ProxyHandler({}))  # direct, whatever HTTP_PROXY says
        # Polled every 10 ms, not 0.5 s: shutdown waits for the next poll.
        self._thread = Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01})

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._released.set()
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()
