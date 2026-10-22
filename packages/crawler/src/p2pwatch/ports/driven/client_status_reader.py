"""``ClientStatusReader``: reads the board of the clients' latest status readings."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from p2pwatch.domain.status_reading import PublishedReading


class ClientStatusReader(ABC):
    """Reads each client's latest status reading, from any thread."""

    @abstractmethod
    def read_readings(self) -> Mapping[str, PublishedReading | None]:
        """Each client's reading, ``None`` before its first."""
