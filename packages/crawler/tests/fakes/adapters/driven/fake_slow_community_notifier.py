import asyncio

from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import NotificationService
from p2pwatch.domain.observability.policy import Audience
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier


class FakeSlowCommunityNotifier(FakeNotifier):
    """Sends the operations' notifications at once and the community's ``held_seconds`` later."""

    def __init__(self, *, held_seconds: float) -> None:
        super().__init__()
        self._held_seconds = held_seconds

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        if service.audience is Audience.COMMUNITY:
            await asyncio.sleep(self._held_seconds)  # noqa: TID251
        await super().notify(service, notification=notification)
