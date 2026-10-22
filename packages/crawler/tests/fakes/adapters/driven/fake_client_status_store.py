from collections.abc import Mapping

from p2pwatch.application.ports.driven.client_status_reader import StatusReadingReader
from p2pwatch.application.ports.driven.client_status_writer import StatusReadingWriter
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import PublishedReading, StatusReading


class FakeStatusReadingStore(StatusReadingWriter, StatusReadingReader):
    """Reads the readings it is given, each replaced by the client's latest reading."""

    def __init__(
        self, published_readings: Mapping[str, PublishedReading | None] | None = None
    ) -> None:
        self._published_readings = dict(published_readings or {})

    def set_reading(
        self, client_name: str, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        self._published_readings[client_name] = PublishedReading(reading, published_at)

    def read_readings(self) -> Mapping[str, PublishedReading | None]:
        return dict(self._published_readings)
