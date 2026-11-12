"""``SearchStartReader``: each client's latest search starts, which survive a restart, in
``local.db``, never merged. Synchronous: a read takes a few milliseconds."""

from abc import ABC, abstractmethod

from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.search.latest_search_start import LatestSearchStart


class SearchStartReader(ABC):
    """Reads a client's latest search starts."""

    @abstractmethod
    def read_latest_starts(self, client_name: ClientName) -> tuple[LatestSearchStart, ...]:
        """``client_name``'s latest start of each channel and scope, ``()`` before the first
        write, each ``started_at`` aware in UTC."""
