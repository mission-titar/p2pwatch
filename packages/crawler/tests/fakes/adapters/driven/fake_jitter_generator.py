from p2pwatch.application.ports.driven.jitter_generator import JitterGenerator


class FakeJitterGenerator(JitterGenerator):
    """DETERMINISTIC jitter: ``jitter`` returns ``jitter_value`` (0.0 by default → backoff/pause =
    exact NOMINAL value), but honors the port CONTRACT like the real ``RandomJitterGenerator``:
    ``span <= 0`` → ``0.0`` (otherwise the min==max pause test would lie about real behavior)."""

    def __init__(self, *, jitter_value: float = 0.0) -> None:
        self._jitter_value = jitter_value
        self.jitter_spans: list[float] = []

    def jitter(self, span: float) -> float:
        self.jitter_spans.append(span)
        if span <= 0:
            return 0.0
        return self._jitter_value
