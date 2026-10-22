import asyncio

from p2pwatch.application.ports.driving.shutdown_requester import ShutdownRequester


class FakeShutdownRequester(ShutdownRequester):
    """Keeps each call by its operation's name, and sets ``requested``, for a test to wait on."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.requested = asyncio.Event()

    def request_shutdown(self) -> None:
        self.calls.append("request_shutdown")
        self.requested.set()
