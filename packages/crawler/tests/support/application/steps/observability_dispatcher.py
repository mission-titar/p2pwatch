"""A real dispatch step over the fakes its outputs land in, for the steps that dispatch."""

import asyncio
from collections.abc import Sequence

from p2pwatch.application.steps.notification_outbox import NotificationOutbox
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.notification import Notification
from p2pwatch.domain.observability.notification_sends import NotificationService
from p2pwatch.domain.observability.policy import Audience
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notification_outbox_store import FakeNotificationOutboxStore
from tests.fakes.adapters.driven.fake_notifier import ONE_SERVICE_PER_AUDIENCE
from tests.fakes.adapters.driven.fake_waker import FakeWaker


class ObservabilityOverFakes:
    """An ``ObservabilityDispatcher`` whose log lines, node metrics and notifications a test
    reads, each notification left in ``outbox`` for the one service of its audience."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.node_metric_store = FakeNodeMetricStore()
        self.outbox_store = FakeNotificationOutboxStore()
        self.outbox = NotificationOutbox(
            writer=self.outbox_store,
            reader=self.outbox_store,
            services=ONE_SERVICE_PER_AUDIENCE,
            waker=FakeWaker(),
            logger=FakeLogger(),
        )
        self.notifications: list[tuple[Audience, Notification]] = []
        # Whether the callback of ``watch_for_a_suspension`` had run, at each notification left.
        self.suspended_before_each_leave: list[bool] = []
        self._suspended = False
        self.dispatcher = ObservabilityDispatcher(
            logger=self.logger,
            node_metric_writer=self.node_metric_store,
            leave_notification=self._leave,
            services=ONE_SERVICE_PER_AUDIENCE,
        )

    @property
    def node_ids(self) -> list[NodeId]:
        return [notification.node_id for _, notification in self.notifications]

    def watch_for_a_suspension(self) -> None:
        """Schedules a callback on the loop, which runs only once the running task suspends,
        such as on a dispatch awaited in a task of its own."""
        asyncio.get_running_loop().call_soon(self._suspend)

    def _suspend(self) -> None:
        self._suspended = True

    def _leave(
        self, notification: Notification, *, services: Sequence[NotificationService]
    ) -> None:
        """Keeps each notification with the audience of each service it is left for, oldest
        first, then leaves it in the outbox."""
        self.suspended_before_each_leave.append(self._suspended)
        self.notifications.extend((service.audience, notification) for service in services)
        self.outbox.leave(notification, services=services)
