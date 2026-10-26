"""A real dispatch step over the fakes its outputs land in, for the steps that dispatch."""

from p2pwatch.application.steps.observability_dispatcher import ObservabilityDispatcher
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_metrics_recorder import FakeMetricsRecorder
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore
from tests.fakes.adapters.driven.fake_notifier import FakeNotifier

_NOTIFICATION_TIMEOUT_SECONDS = 5.0


class ObservabilityOverFakes:
    """An ``ObservabilityDispatcher`` whose log lines, node metrics and notifications a test
    reads."""

    def __init__(self) -> None:
        self.logger = FakeLogger()
        self.node_metric_store = FakeNodeMetricStore()
        self.notifier = FakeNotifier()
        self.dispatcher = ObservabilityDispatcher(
            logger=self.logger,
            metrics_recorder=FakeMetricsRecorder(),
            node_metric_writer=self.node_metric_store,
            notifier=self.notifier,
            notification_timeout_seconds=_NOTIFICATION_TIMEOUT_SECONDS,
        )
