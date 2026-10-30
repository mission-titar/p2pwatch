"""``InMemoryStatusReadingStore``: each client's latest reading, published by its status loop and
read on the webui's thread."""

from collections.abc import Iterable, Mapping

from p2pwatch.application.ports.driven.status_reading_reader import StatusReadingReader
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import PublishedReading, StatusReading


class InMemoryStatusReadingStore(StatusReadingWriter, StatusReadingReader):
    """Holds no clock: each reading comes with the instant it was published at."""

    def __init__(self, client_names: Iterable[ClientName]) -> None:
        self._published_readings: Mapping[ClientName, PublishedReading | None] = dict.fromkeys(
            client_names
        )

    def set_reading(
        self, client_name: ClientName, *, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        # A new map, never a mutation: the other thread reads whole snapshots, no lock needed.
        self._published_readings = {
            **self._published_readings,
            client_name: PublishedReading(reading=reading, published_at=published_at),
        }

    def read_readings(self) -> Mapping[ClientName, PublishedReading | None]:
        return self._published_readings
