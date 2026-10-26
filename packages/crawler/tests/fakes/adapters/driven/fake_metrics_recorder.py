from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.domain.observability.node_metric import CounterIncrement, GaugeSetting


class FakeMetricsRecorder(MetricsRecorder):
    def __init__(self) -> None:
        self.applied: list[CounterIncrement | GaugeSetting] = []

    def apply(self, instruction: CounterIncrement | GaugeSetting) -> None:
        self.applied.append(instruction)
