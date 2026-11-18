"""A real dispatch step over the fakes its outputs land in, for the steps that dispatch."""

from collections.abc import Sequence

from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import NotificationService
from p2pwatch.domain.observability.policy import Audience
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE
from tests.fakes.adapters.driven.fake_waker import FakeWaker


class ObservabilityOverFakes:
    """An ``ObservabilityDispatcher`` whose log lines, node metrics and notifications a test
    reads, each notification left in ``outbox`` for the one service of its audience."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.node_metric_store = FakeNodeMetricStore()
        self.outbox = NotificationOutbox(waker=FakeWaker())
        self.notifications: list[tuple[Audience, Notification]] = []
        self.dispatcher = ObservabilityDispatcher(
            logger=self.logger,
            node_metric_writer=self.node_metric_store,
            leave_notification=self._leave,
            services=ONE_SERVICE_PER_AUDIENCE,
        )

    @property
    def node_ids(self) -> list[NodeId]:
        return [notification.node_id for _, notification in self.notifications]

    def _leave(
        self, notification: Notification, *, services: Sequence[NotificationService]
    ) -> None:
        """Keeps each notification with the audience of each service it is left for, oldest
        first, then leaves it in the outbox."""
        self.notifications.extend((service.audience, notification) for service in services)
        self.outbox.leave(notification, services=services)
