"""``RandomJitterGenerator``: the ``JitterGenerator`` port's jitter draw, over ``random.Random``."""

import random

from p2pwatch.application.ports.driven.jitter_generator import JitterGenerator


class RandomJitterGenerator(JitterGenerator):
    """Real ``JitterGenerator``.

    ``jitter``: REAL draw in ``[0, span)`` via a dedicated ``random.Random`` instance,
    seeded at construction (``jitter_seed``, ``None`` for the system's entropy): the backoff
    jitter breaks the thundering-herd between nodes/channels."""

    def __init__(self, *, jitter_seed: int | str | None) -> None:
        self._random = random.Random(jitter_seed)

    def jitter(self, span: float) -> float:
        """Float in ``[0, span)`` (``[0.0]`` if ``span <= 0``)."""
        if span <= 0:
            return 0.0
        return self._random.uniform(0.0, span)
