"""``UvicornServerThread``: the webui served by uvicorn on a thread and an event loop of its own."""

import asyncio
import logging
import socket
import threading
from collections.abc import Iterable
from contextlib import AbstractContextManager, ExitStack

import uvicorn
from starlette.applications import Starlette

_logger = logging.getLogger(__name__)


class _StartReportingServer(uvicorn.Server):
    """A ``uvicorn.Server`` that sets ``settled`` once its socket is bound."""

    def __init__(self, config: uvicorn.Config, settled: threading.Event) -> None:
        super().__init__(config)
        self._settled = settled

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        self._settled.set()


class UvicornServerThread:
    """Serves the webui on a daemon thread: a failure degrades the webui, never the crawler."""

    def __init__(
        self,
        app: Starlette,
        address: tuple[str, int],
        *,
        start_timeout_seconds: float,
        join_timeout_seconds: float,
        serving_resources: Iterable[AbstractContextManager[object]],
    ) -> None:
        host, port = address
        self._serving_resources = tuple(serving_resources)
        self._settled = threading.Event()
        self._server = _StartReportingServer(
            uvicorn.Config(app, host=host, port=port, log_level="info"), self._settled
        )
        self._thread = threading.Thread(target=self._serve, name="webui", daemon=True)
        self._start_timeout_seconds = start_timeout_seconds
        self._join_timeout_seconds = join_timeout_seconds

    @property
    def bound_address(self) -> tuple[str, int]:
        host, port = self._server.servers[0].sockets[0].getsockname()[:2]
        return host, port

    async def start(self) -> None:
        """Starts the thread, then waits, bounded, until uvicorn has bound or the thread ended."""
        self._thread.start()
        settled = await asyncio.to_thread(self._settled.wait, self._start_timeout_seconds)
        if not settled:
            _logger.error(
                "webui degraded: uvicorn did not start within %s s", self._start_timeout_seconds
            )
        elif self._server.started:
            _logger.info("webui serving on %s:%d (own thread)", *self.bound_address)

    async def stop(self) -> None:
        """Asks uvicorn to exit, then joins off the event loop so a shutdown deadline can cancel."""
        self._server.should_exit = True
        await asyncio.to_thread(self._thread.join, self._join_timeout_seconds)

    def _serve(self) -> None:
        # uvicorn ends a failed bind with ``sys.exit``, whose traceback chains the ``OSError``.
        try:
            # Entered and left on this thread: what they hold may be thread-affine.
            with ExitStack() as stack:
                for resource in self._serving_resources:
                    stack.enter_context(resource)
                asyncio.run(self._server.serve())
        except (Exception, SystemExit) as error:
            _logger.error("webui degraded: the crawler carries on without HTTP", exc_info=error)
        finally:
            self._settled.set()
