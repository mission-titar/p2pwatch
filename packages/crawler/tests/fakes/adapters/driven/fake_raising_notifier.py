from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.policy import Audience


class FakeRaisingNotifier(Notifier):
    """Raises ``error`` at every send, such as a refusal or a bug of its own, counting the sends."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self.sends = 0

    async def notify(self, audience: Audience, *, notification: Notification) -> None:
        self.sends += 1
        raise self._error
