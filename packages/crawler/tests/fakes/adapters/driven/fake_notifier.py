from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.policy import Audience


class FakeNotifier(Notifier):
    def __init__(self) -> None:
        self.calls: list[tuple[Audience, Notification]] = []

    @property
    def node_ids(self) -> list[str]:
        return [notification.node_id for _, notification in self.calls]

    async def notify(self, audience: Audience, notification: Notification) -> None:
        self.calls.append((audience, notification))
