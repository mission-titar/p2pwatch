from collections.abc import Mapping

from p2pwatch.application.ports.driven.client_status_reader import ClientStatusReader
from p2pwatch.domain.status_reading import PublishedReading


class FakeClientStatusReader(ClientStatusReader):
    """Reads the readings it is given."""

    def __init__(self, published_readings: Mapping[str, PublishedReading | None]) -> None:
        self._published_readings = published_readings

    def read_readings(self) -> Mapping[str, PublishedReading | None]:
        return self._published_readings
