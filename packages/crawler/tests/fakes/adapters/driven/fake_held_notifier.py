import asyncio

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import NotificationService
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier


class FakeHeldNotifier(FakeNotifier):
    """Holds each send until it is cancelled, so a test can cancel the caller mid-send;
    ``reached`` is set once a send is held."""

    def __init__(self) -> None:
        super().__init__()
        self.reached = asyncio.Event()

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        self.reached.set()
        await asyncio.Event().wait()
