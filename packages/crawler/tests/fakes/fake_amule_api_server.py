import socket
import threading
from typing import Protocol, Self

import httpx
import uvicorn
from starlette.types import Receive, Scope, Send

from tests.fakes.fake_amule_api import FakeAmuleApi


class ApiPredicate(Protocol):
    def __call__(self, api: FakeAmuleApi, /) -> bool: ...


class FakeAmuleApiServer:
    """``FakeAmuleApi`` served over HTTP on a loopback port, by uvicorn in a thread of its own.

    A request the fake refuses answers 500, and the first refusal is raised again on exit."""

    def __init__(self, api: FakeAmuleApi) -> None:
        self.api = api
        # Listening before uvicorn starts: a client connecting early waits in the backlog.
        self._socket = socket.create_server(("127.0.0.1", 0))
        self.host, self.port = self._socket.getsockname()[:2]
        self.failures: list[Exception] = []
        self._served = threading.Condition()
        config = uvicorn.Config(
            self._serve_http, interface="asgi3", lifespan="off", log_config=None, access_log=False
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, args=([self._socket],))

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._server.should_exit = True
        self._thread.join()
        self._socket.close()
        if self.failures:
            raise self.failures[0]

    def wait_for(self, predicate: ApiPredicate, *, timeout_seconds: float) -> bool:
        """Blocks until ``predicate`` holds after a request, as ``Condition.wait_for`` does."""
        with self._served:
            return self._served.wait_for(lambda: predicate(self.api), timeout_seconds)

    async def _serve_http(  # noqa: PLR0917
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)
        query = scope["query_string"].decode()
        request = httpx.Request(
            scope["method"],
            f"http://{self.host}:{self.port}{scope['path']}?{query}",
            headers=scope["headers"],
            content=body,
        )
        with self._served:
            try:
                response = self.api.handle(request)
            except Exception as failure:
                self.failures.append(failure)
                response = httpx.Response(500)
            self._served.notify_all()
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": response.headers.raw,
            }
        )
        await send({"type": "http.response.body", "body": response.content})
