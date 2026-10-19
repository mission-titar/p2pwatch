"""``BackoffStateRepository`` port: the search backoff, which survives a restart, in ``local.db``
(never merged). Synchronous, as ``LocalStateRepository``: a write takes under a millisecond."""

from typing import Protocol

# Imported from here too until block 180 moves their importers to the domain.
from p2pwatch.domain.search.backoff import BackoffKey as BackoffKey
from p2pwatch.domain.search.backoff import BackoffState as BackoffState


class BackoffStateRepository(Protocol):
    """``save_backoff_states`` replaces every state saved before; ``load_backoff_states`` returns
    ``{}`` before the first save."""

    def load_backoff_states(self) -> dict[BackoffKey, BackoffState]: ...

    def save_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None: ...
