"""``BackoffStateRepository`` port: the search backoff, which survives a restart, in ``local.db``
(never merged). Synchronous, as ``LocalStateRepository``: a write takes under a millisecond."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


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


class BackoffStateRepository(Protocol):
    """``save_backoff_states`` replaces every state saved before; ``load_backoff_states`` returns
    ``{}`` before the first save."""

    def load_backoff_states(self) -> dict[BackoffKey, BackoffState]: ...

    def save_backoff_states(self, backoff: dict[BackoffKey, BackoffState]) -> None: ...
