from datetime import UTC, datetime

from p2pwatch.adapters.driven.in_memory_status_board import InMemoryStatusBoard
from p2pwatch.domain.status_reading import ClientStatus, StatusReading
from p2pwatch.ports.driven.client_status import (
    ClientStatusReader,
    ClientStatusWriter,
    PublishedReading,
)
from p2pwatch.ports.driven.clock import MonotonicInstant

_READING = StatusReading(datetime(2026, 6, 12, tzinfo=UTC), ClientStatus("3.0.1", ()))


def _board() -> tuple[ClientStatusWriter, ClientStatusReader]:
    """The board seen through its two ports."""
    board = InMemoryStatusBoard(("amuled",))
    return board, board


def test_a_client_not_read_yet_reads_none() -> None:
    _writer, reader = _board()
    assert reader.read_readings() == {"amuled": None}


def test_a_published_reading_is_read_with_its_instant() -> None:
    writer, reader = _board()
    writer.publish("amuled", _READING, MonotonicInstant(7))
    assert reader.read_readings() == {"amuled": PublishedReading(_READING, MonotonicInstant(7))}


def test_publishing_replaces_the_snapshot_and_never_changes_one_already_read() -> None:
    writer, reader = _board()
    before = reader.read_readings()
    writer.publish("amuled", _READING, MonotonicInstant(7))
    assert before == {"amuled": None}
