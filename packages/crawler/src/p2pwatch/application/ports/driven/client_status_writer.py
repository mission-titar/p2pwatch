"""``ClientStatusWriter``: publishes to the board of the clients' latest status readings."""

from abc import ABC, abstractmethod

from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import StatusReading


class ClientStatusWriter(ABC):
    """Publishes each client's latest status reading, from its status loop."""

    @abstractmethod
    def publish(
        self, client_name: str, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        """Replaces the client's reading."""
