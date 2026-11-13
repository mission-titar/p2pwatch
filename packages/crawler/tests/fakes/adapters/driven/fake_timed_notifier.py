from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import NotificationService
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE
from tests.fakes.adapters.driven.fake_time import FakeTime


class FakeTimedNotifier(Notifier):
    """Each notification with the seconds elapsed on the monotonic clock when it was sent."""

    def __init__(self, fake_time: FakeTime) -> None:
        self._fake_time = fake_time
        self._start = fake_time.monotonic.now()
        self.notifications: list[tuple[float, Notification]] = []

    def services(self) -> tuple[NotificationService, ...]:
        return ONE_SERVICE_PER_AUDIENCE

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        elapsed = self._fake_time.monotonic.now() - self._start
        self.notifications.append((elapsed.total_seconds(), notification))
