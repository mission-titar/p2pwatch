"""The promise of the ``StatusReadingReader`` and ``StatusReadingWriter`` pair."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Protocol

import pytest

from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import ClientStatus, PublishedReading, StatusReading

CLIENT_NAMES = ("amuled", "emule")
_READING = StatusReading(datetime(2026, 6, 12, tzinfo=UTC), ClientStatus("3.0.1", ()))
_SILENT_READING = StatusReading(datetime(2026, 6, 12, 0, 1, tzinfo=UTC), None)


class StatusReadingStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def set_reading(
        self, client_name: str, reading: StatusReading, published_at: MonotonicInstant
    ) -> None: ...

    def read_readings(self) -> Mapping[str, PublishedReading | None]: ...


class StatusReadingStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def status_reading_store(self) -> StatusReadingStore:
        """A store built with ``CLIENT_NAMES``, no reading set yet."""

    def test_every_client_is_listed_without_a_reading_before_its_first(
        self, status_reading_store: StatusReadingStore
    ) -> None:
        assert status_reading_store.read_readings() == {"amuled": None, "emule": None}

    def test_a_reading_is_read_with_its_instant(
        self, status_reading_store: StatusReadingStore
    ) -> None:
        status_reading_store.set_reading("amuled", _READING, MonotonicInstant(7))
        assert status_reading_store.read_readings() == {
            "amuled": PublishedReading(_READING, MonotonicInstant(7)),
            "emule": None,
        }

    def test_a_reading_replaces_the_clients_previous_one(
        self, status_reading_store: StatusReadingStore
    ) -> None:
        status_reading_store.set_reading("amuled", _READING, MonotonicInstant(7))
        status_reading_store.set_reading("amuled", _SILENT_READING, MonotonicInstant(8))
        assert status_reading_store.read_readings()["amuled"] == PublishedReading(
            _SILENT_READING, MonotonicInstant(8)
        )

    def test_a_reading_is_read_from_another_thread(
        self, status_reading_store: StatusReadingStore
    ) -> None:
        status_reading_store.set_reading("amuled", _READING, MonotonicInstant(7))
        with ThreadPoolExecutor(max_workers=1) as executor:
            published_readings = executor.submit(status_reading_store.read_readings).result()
        assert published_readings["amuled"] == PublishedReading(_READING, MonotonicInstant(7))
