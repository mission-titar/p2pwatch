from p2pwatch.domain.observability.node_metric import CounterIncrement
from tests.fakes.adapters.driven.fake_node_metric_store import FakeNodeMetricStore


class FakeRaisingNodeMetricStore(FakeNodeMetricStore):
    """Raises ``bug`` at each counter it is given, as a bug in the metrics would."""

    def __init__(self, bug: Exception) -> None:
        super().__init__()
        self._bug = bug

    def record_increment(self, increment: CounterIncrement) -> None:
        raise self._bug
