from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.policy import Audience


class FakeRaisingNotifier(Notifier):
    """Raises ``error`` at every notification, counting them."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.calls = 0

    async def notify(self, audience: Audience, *, notification: Notification) -> None:
        self.calls += 1
        raise self._error
