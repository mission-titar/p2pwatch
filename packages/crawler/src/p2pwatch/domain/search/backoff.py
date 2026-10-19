"""Capped exponential backoff, PURE math, and the wait it persists (spec orchestration §3/§4).

PURE domain: no I/O, no global ``random``, no clock. ``backoff_delay`` computes the
NOMINAL delay (exponential bounded by ``cap``); the JITTER is applied by the caller (it
needs the ``Rng`` port / a draw): separating the deterministic computation from the draw
keeps this module trivially testable and the jitter replayable. Used by
``application/search_worker.py`` for the PER (client, channel) backoff (spec §3).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class BackoffKey:
    """What a backoff holds back: one channel of a client, or the whole client (``None``)."""

    client_name: str
    channel: str | None


@dataclass(frozen=True)
class BackoffState:
    """A persisted wait: ``attempts`` consecutive failures, the latest of which started a wait of
    ``delay`` at ``started_at`` on the wall clock."""

    attempts: int
    started_at: datetime
    delay: timedelta


def backoff_delay(attempt: int, *, base: float, cap: float, factor: float) -> float:
    """Backoff delay for the ``attempt``-th consecutive failed attempt (≥ 1).

    ``attempt = 1`` → ``base``; each additional failure multiplies by ``factor``; the
    result is capped at ``cap`` (spec MVP §6: "exponential backoff"). An ``attempt`` of 0
    or negative is treated as the first attempt (``base``) — a caller must never request a
    delay for "zero failures", but we do not crash on an out-of-bounds input (resilience,
    spec §14).
    """
    if attempt <= 1:
        return min(base, cap)
    return min(base * factor ** (attempt - 1), cap)
