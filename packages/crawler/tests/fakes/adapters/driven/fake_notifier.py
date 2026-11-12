from p2pwatch.application.ports.driven.notifier import Notifier
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notifier_outcomes import NotificationRefused, NotificationService
from p2pwatch.domain.observability.policy import Audience

ONE_SERVICE_PER_AUDIENCE = tuple(
    NotificationService(scheme="fake", audience=audience) for audience in Audience
)


class FakeNotifier(Notifier):
    """Keeps each notification with the audience of the service it was sent to; ``refusing``,
    refuses every send instead."""

    def __init__(
        self,
        services: tuple[NotificationService, ...] = ONE_SERVICE_PER_AUDIENCE,
        *,
        refusing: bool = False,
    ) -> None:
        self._services = services
        self._refusing = refusing
        self.calls: list[tuple[Audience, Notification]] = []

    @property
    def node_ids(self) -> list[NodeId]:
        return [notification.node_id for _, notification in self.calls]

    def services(self) -> tuple[NotificationService, ...]:
        return self._services

    async def notify(self, service: NotificationService, *, notification: Notification) -> None:
        if self._refusing:
            raise NotificationRefused("refused")
        self.calls.append((service.audience, notification))
