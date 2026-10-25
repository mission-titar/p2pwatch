"""``StatusReadingReader``: reads the clients' latest status readings."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from p2pwatch.domain.status_reading import PublishedReading


class StatusReadingReader(ABC):
    """Reads each client's latest status reading, from any thread."""

    @abstractmethod
    def read_readings(self) -> Mapping[str, PublishedReading | None]:
        """Each client the store was built with, its reading ``None`` before its first."""
