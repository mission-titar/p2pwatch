"""Randomness, injectable: ``JitterGenerator`` draws the backoff's jitter."""

from abc import ABC, abstractmethod


class JitterGenerator(ABC):
    """Draws the backoff's jitter."""

    @abstractmethod
    def jitter(self, span: float) -> float:
        """A float in ``[0, span)``, ``0.0`` when ``span <= 0``."""
