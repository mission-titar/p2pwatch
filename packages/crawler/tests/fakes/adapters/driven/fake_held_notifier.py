import asyncio

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import NotificationService
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier


class FakeHeldNotifier(FakeNotifier):
    """Holds each send until the test releases it: ``reached`` set once one is held, ``sent`` once
    one is kept."""

    def __init__(self) -> None:
        super().__init__()
        self.reached = asyncio.Event()
        self.released = asyncio.Event()
        self.sent = asyncio.Event()

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        self.reached.set()
        await self.released.wait()
        await super().notify(service, notification=notification)
        self.sent.set()
