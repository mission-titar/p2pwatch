"""A real dispatch step over the fakes its outputs land in, for the steps that dispatch."""

from p2pwatch.application.steps.node_health import NodeHealth
from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from p2pwatch.domain.observability.notification_sends import notification_service_dependencies
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier

_NOTIFICATION_TIMEOUT_SECONDS = 5.0


class ObservabilityOverFakes:
    """An ``ObservabilityDispatcher`` whose log lines, node metrics and notifications a test
    reads, each send recorded on a part of its own for each service of the notifier."""

    def __init__(self, *, notifier: FakeNotifier | None = None) -> None:
        self.logger = FakeLogger()
        self.node_metric_store = FakeNodeMetricStore()
        self.notifier = notifier or FakeNotifier()
        self.dispatcher = ObservabilityDispatcher(
            logger=self.logger,
            node_metric_writer=self.node_metric_store,
            current_notifier=lambda: self.notifier,
            notification_timeout_seconds=_NOTIFICATION_TIMEOUT_SECONDS,
            record_check=NodeHealth(logger=FakeLogger(), subscribers=()).record,
            service_dependencies=notification_service_dependencies(self.notifier.services()),
        )
