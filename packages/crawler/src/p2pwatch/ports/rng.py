"""Randomness, injectable: ``Rng`` draws the backoff's jitter."""

from typing import Protocol


class Rng(Protocol):
    """Injectable randomness: ``jitter`` returns a float in ``[0, span)`` (backoff jitter)."""

    def jitter(self, span: float) -> float: ...
