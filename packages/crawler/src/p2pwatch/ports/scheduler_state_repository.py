"""``SchedulerStateRepository`` port: the scheduler's durable state (spec §4/§7).

PORTS layer, SYNCHRONOUS Protocol (same principle as ``LocalStateRepository``: sub-ms, no
``to_thread`` in the MVP). Persists the per-(client, channel) BACKOFF (spec §3/§7: it
must survive a restart), as KV in the ``scheduler_state`` table of ``local.db`` (never
merged, invariant §11).

The backoff is a map of :class:`BackoffKey` to :class:`BackoffState`, where the key is one channel
of a client (a channel failure) or the whole client (reconnection).
``load_backoff_states`` returns an empty dict if never written (first startup).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class BackoffKey:
    """What a backoff holds back: one channel of a client, or the whole client (``None``)."""

    client_name: str
    channel: str | None


@dataclass(frozen=True)
class BackoffState:
    """Backoff state of a :class:`BackoffKey`: counter + deadline.

    ``attempts`` = number of CONSECUTIVE failures (used for the exponential computation).
    ``retry_after`` = fixed-width ISO-8601 UTC: as long as ``now < retry_after``, the key is
    SKIPPED. Frozen and JSON-friendly (two scalar fields) → trivial serialization.
    """

    attempts: int
    retry_after: str


class SchedulerStateRepository(Protocol):
    """Sync scheduling-state contract (the backoff).

    ``save_backoff_states`` ENTIRELY replaces the persisted map (registry snapshot).
    """

    def load_backoff_states(self) -> dict[BackoffKey, BackoffState]: ...

    def save_backoff_states(self, backoff: dict[BackoffKey, BackoffState]) -> None: ...
