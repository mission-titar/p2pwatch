import asyncio

from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import NotificationService
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE


class FakeHangingNotifier(Notifier):
    """Its ``notify`` sleeps past the short timeout of the test that uses it."""

    def __init__(
        self, services: tuple[NotificationService, ...] = ONE_SERVICE_PER_AUDIENCE
    ) -> None:
        self._services = services

    def services(self) -> tuple[NotificationService, ...]:
        return self._services

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        await asyncio.sleep(10)  # noqa: TID251
