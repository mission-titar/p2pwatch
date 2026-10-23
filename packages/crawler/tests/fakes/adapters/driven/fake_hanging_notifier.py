import asyncio

from p2pwatch.domain.observability.notification import Notification

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.policy import Audience


class FakeHangingNotifier(Notifier):
    async def notify(self, audience: Audience, notification: Notification) -> None:
        await asyncio.sleep(10)  # exceeds the test's short timeout
