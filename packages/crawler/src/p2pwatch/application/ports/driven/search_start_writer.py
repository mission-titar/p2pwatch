"""``SearchStartWriter``: each client's latest search starts, kept in ``local.db`` so that they
survive a restart, never merged. Synchronous: a write takes a few milliseconds."""

from abc import ABC, abstractmethod

from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.search.latest_search_start import LatestSearchStart


class SearchStartWriter(ABC):
    """Writes a client's latest search starts."""

    @abstractmethod
    def set_latest_start(self, client_name: ClientName, *, start: LatestSearchStart) -> None:
        """Replaces ``client_name``'s start in the channel and scope of ``start`` with it."""
