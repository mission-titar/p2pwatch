from p2pwatch.application.ports.driven.metrics_recorder import MetricsRecorder
from p2pwatch.domain.observability.policy import MetricInstruction


class FakeMetricsRecorder(MetricsRecorder):
    def __init__(self) -> None:
        self.applied: list[MetricInstruction] = []

    def apply(self, instruction: MetricInstruction) -> None:
        self.applied.append(instruction)
