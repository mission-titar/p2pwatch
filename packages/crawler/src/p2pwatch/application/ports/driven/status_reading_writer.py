"""``StatusReadingWriter``: sets each client's latest status reading."""

from abc import ABC, abstractmethod

from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import StatusReading


class StatusReadingWriter(ABC):
    """Publishes each client's latest status reading, from its status loop."""

    @abstractmethod
    def set_reading(
        self, client_name: ClientName, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        """Replaces the client's reading."""
