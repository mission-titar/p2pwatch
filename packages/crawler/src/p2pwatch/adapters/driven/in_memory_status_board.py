"""``InMemoryStatusBoard``: each client's latest reading, published by its status loop and read
on the webui's thread (D21)."""

from collections.abc import Iterable, Mapping

from p2pwatch.ports.driven.client_status import (
    ClientStatusReader,
    ClientStatusWriter,
    PublishedReading,
    StatusReading,
)
from p2pwatch.ports.driven.clock import MonotonicInstant


class InMemoryStatusBoard(ClientStatusWriter, ClientStatusReader):
    """Holds no clock: each reading comes with the instant it was published at."""

    def __init__(self, client_names: Iterable[str]) -> None:
        self._published_readings: Mapping[str, PublishedReading | None] = dict.fromkeys(
            client_names
        )

    def publish(
        self, client_name: str, reading: StatusReading, published_at: MonotonicInstant
    ) -> None:
        # A new map, never a mutation: the other thread reads whole snapshots, no lock needed.
        self._published_readings = {
            **self._published_readings,
            client_name: PublishedReading(reading, published_at),
        }

    def read_readings(self) -> Mapping[str, PublishedReading | None]:
        return self._published_readings
