import asyncio
import contextlib

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.policy import Audience
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier


class FakeHeldNotifier(FakeNotifier):
    """Holds each send until the test releases it, so a test can cancel the caller mid-send;
    ``reached`` is set once a send is held, and a send kept only once released."""

    def __init__(self) -> None:
        super().__init__()
        self.reached = asyncio.Event()
        self.released = asyncio.Event()
        self._sent = asyncio.Event()

    async def notify(self, audience: Audience, *, notification: Notification) -> None:
        self.reached.set()
        await self.released.wait()
        await super().notify(audience, notification=notification)
        self._sent.set()

    async def wait_until_sent(self, *, timeout_seconds: float) -> None:
        """Returns once a send is kept, or after ``timeout_seconds`` with nothing kept."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._sent.wait(), timeout=timeout_seconds)
