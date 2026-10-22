from datetime import UTC, datetime

from p2pwatch.adapters.driven.in_memory_status_reading_store import InMemoryStatusReadingStore
from p2pwatch.application.ports.driven.status_reading_reader import StatusReadingReader
from p2pwatch.application.ports.driven.status_reading_writer import StatusReadingWriter
from p2pwatch.domain.monotonic_instant import MonotonicInstant
from p2pwatch.domain.status_reading import ClientStatus, PublishedReading, StatusReading

_READING = StatusReading(datetime(2026, 6, 12, tzinfo=UTC), ClientStatus("3.0.1", ()))


def _status_reading_store() -> tuple[StatusReadingWriter, StatusReadingReader]:
    """The board seen through its two ports."""
    status_reading_store = InMemoryStatusReadingStore(("amuled",))
    return status_reading_store, status_reading_store


def test_a_client_not_read_yet_reads_none() -> None:
    _writer, reader = _status_reading_store()
    assert reader.read_readings() == {"amuled": None}


def test_a_published_reading_is_read_with_its_instant() -> None:
    writer, reader = _status_reading_store()
    writer.set_reading("amuled", _READING, MonotonicInstant(7))
    assert reader.read_readings() == {"amuled": PublishedReading(_READING, MonotonicInstant(7))}


def test_publishing_replaces_the_snapshot_and_never_changes_one_already_read() -> None:
    writer, reader = _status_reading_store()
    before = reader.read_readings()
    writer.set_reading("amuled", _READING, MonotonicInstant(7))
    assert before == {"amuled": None}
