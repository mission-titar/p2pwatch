"""``BackoffStateReader``: the search backoff, which survives a restart, in ``local.db``,
never merged. Synchronous: a read takes under a millisecond."""

from abc import ABC, abstractmethod

from p2pwatch.domain.search.backoff import BackoffKey, BackoffState


class BackoffStateReader(ABC):
    """Reads the backoff states saved last."""

    @abstractmethod
    def read_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        """The states saved last, ``{}`` before the first save, each ``started_at`` aware in UTC."""
