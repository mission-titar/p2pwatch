from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import NotificationService
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE


class FakeRaisingNotifier(Notifier):
    """Raises ``error`` at every notification, counting them."""

    def __init__(
        self,
        error: Exception,
        *,
        services: tuple[NotificationService, ...] = ONE_SERVICE_PER_AUDIENCE,
    ) -> None:
        self._error = error
        self._services = services
        self.calls = 0

    def services(self) -> tuple[NotificationService, ...]:
        return self._services

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        self.calls += 1
        raise self._error
