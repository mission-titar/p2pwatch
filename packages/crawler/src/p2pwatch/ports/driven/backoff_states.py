"""The search backoff, which survives a restart, in ``local.db`` (never merged). Synchronous, as
the policy fingerprint's ports: a write takes under a millisecond."""

from abc import ABC, abstractmethod

from p2pwatch.domain.search.backoff import BackoffKey, BackoffState


class BackoffStateReader(ABC):
    """Reads the backoff states saved last."""

    @abstractmethod
    def read_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        """The states saved last, ``{}`` before the first save."""


class BackoffStateWriter(ABC):
    """Saves the search backoff's states."""

    @abstractmethod
    def save_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None:
        """Replaces every state saved before with ``backoff_state_by_key``."""
