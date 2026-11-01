"""The promise of the ``StatusReadingReader`` and ``StatusReadingWriter`` pair."""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from p2pwatch.application.ports.driven.status_reading_reader import StatusReadingReader
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import ClientStatus, PublishedReading, StatusReading

CLIENT_NAMES = (ClientName("amuled"), ClientName("emule"))
_READING = StatusReading(
    read_at=datetime(2026, 6, 12, tzinfo=UTC), status=ClientStatus(version="3.0.1", channels=())
)
_SILENT_READING = StatusReading(read_at=datetime(2026, 6, 12, 0, 1, tzinfo=UTC), status=None)


class StatusReadingStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> StatusReadingWriter:
        """The writer of a store built with ``CLIENT_NAMES``, no reading set yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> StatusReadingReader:
        """The reader of the writer's store."""

    def test_every_client_is_listed_without_a_reading_before_its_first(
        self, reader: StatusReadingReader
    ) -> None:
        assert reader.read_readings() == {"amuled": None, "emule": None}

    def test_a_reading_is_read_with_its_instant(
        self, *, writer: StatusReadingWriter, reader: StatusReadingReader
    ) -> None:
        writer.set_reading(
            ClientName("amuled"), reading=_READING, published_at=MonotonicInstant(nanoseconds=7)
        )
        assert reader.read_readings() == {
            "amuled": PublishedReading(
                reading=_READING, published_at=MonotonicInstant(nanoseconds=7)
            ),
            "emule": None,
        }

    def test_a_reading_replaces_the_clients_previous_one(
        self, *, writer: StatusReadingWriter, reader: StatusReadingReader
    ) -> None:
        writer.set_reading(
            ClientName("amuled"), reading=_READING, published_at=MonotonicInstant(nanoseconds=7)
        )
        writer.set_reading(
            ClientName("amuled"),
            reading=_SILENT_READING,
            published_at=MonotonicInstant(nanoseconds=8),
        )
        assert reader.read_readings()[ClientName("amuled")] == PublishedReading(
            reading=_SILENT_READING, published_at=MonotonicInstant(nanoseconds=8)
        )

    def test_a_reading_is_read_from_another_thread(
        self, *, writer: StatusReadingWriter, reader: StatusReadingReader
    ) -> None:
        writer.set_reading(
            ClientName("amuled"), reading=_READING, published_at=MonotonicInstant(nanoseconds=7)
        )
        with ThreadPoolExecutor(max_workers=1) as executor:
            published_readings = executor.submit(reader.read_readings).result()
        assert published_readings[ClientName("amuled")] == PublishedReading(
            reading=_READING, published_at=MonotonicInstant(nanoseconds=7)
        )
