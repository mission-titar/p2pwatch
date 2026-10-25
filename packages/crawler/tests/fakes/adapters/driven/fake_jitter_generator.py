from p2pwatch.application.ports.driven.jitter_generator import JitterGenerator


class FakeJitterGenerator(JitterGenerator):
    """Draws ``jitter_value``, ``0.0`` by default, and ``0.0`` when ``span <= 0`` as its port
    states; keeps each span it is asked for."""

    def __init__(self, *, jitter_value: float = 0.0) -> None:
        self._jitter_value = jitter_value
        self.jitter_spans: list[float] = []

    def jitter(self, span: float) -> float:
        self.jitter_spans.append(span)
        if span <= 0:
            return 0.0
        return self._jitter_value
