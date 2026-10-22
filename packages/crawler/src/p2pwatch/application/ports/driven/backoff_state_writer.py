"""``BackoffStateWriter``: the search backoff, which survives a restart, in ``local.db``,
never merged. Synchronous: a write takes under a millisecond."""

from abc import ABC, abstractmethod

from p2pwatch.domain.search.backoff import BackoffKey, BackoffState


class BackoffStateWriter(ABC):
    """Saves the search backoff's states."""

    @abstractmethod
    def set_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None:
        """Replaces every state saved before with ``backoff_state_by_key``."""
