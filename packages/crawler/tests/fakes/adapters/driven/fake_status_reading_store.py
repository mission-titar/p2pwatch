from collections.abc import Iterable, Mapping

from p2pwatch.application.ports.driven.status_reading_reader import StatusReadingReader
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import PublishedReading, StatusReading


class FakeStatusReadingStore(StatusReadingWriter, StatusReadingReader):
    """Readings in a dict, each read a copy of it."""

    def __init__(self, client_names: Iterable[ClientName]) -> None:
        self._published_readings: dict[ClientName, PublishedReading | None] = dict.fromkeys(
            client_names
        )

    def set_reading(
        self, client_name: ClientName, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        self._published_readings[client_name] = PublishedReading(reading, published_at)

    def read_readings(self) -> Mapping[ClientName, PublishedReading | None]:
        return dict(self._published_readings)
