import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.micros import (
    instant_to_micros,
    micros_to_instant,
)
from p2pwatch.adapters.driven.persistence_sqlite.variants import register_sql_functions
from tests.support.adapters.driven.persistence_sqlite.named_row import rows

_INSTANT = datetime(2026, 6, 11, 12, 0, 0, 123456, tzinfo=UTC)
_MICROS = 1_781_179_200_123_456


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", autocommit=True)
    register_sql_functions(connection)
    yield connection
    connection.close()


def _iso_to_micros(connection: sqlite3.Connection, stamp: str) -> int:
    """``iso_to_micros`` as the migrations call it, the one way it is called."""
    [row] = rows(connection, "SELECT iso_to_micros(?) AS micros", (stamp,))
    micros: int = row["micros"]
    return micros


def test_instant_to_micros_counts_microseconds_since_the_epoch() -> None:
    assert instant_to_micros(datetime(1970, 1, 1, 0, 0, 0, 1, tzinfo=UTC)) == 1


def test_instant_to_micros_normalizes_an_offset_to_utc() -> None:
    paris = timezone(timedelta(hours=2))
    assert instant_to_micros(datetime(2026, 6, 11, 14, 0, 0, 123456, tzinfo=paris)) == _MICROS


def test_instant_to_micros_refuses_a_naive_instant() -> None:
    with pytest.raises(ValueError, match=r"^instant_to_micros requires an aware datetime$"):
        instant_to_micros(datetime(2026, 6, 11, 12, 0, 0, 123456))


def test_micros_to_instant_is_the_aware_utc_instant() -> None:
    instant = micros_to_instant(_MICROS)
    assert instant == _INSTANT
    assert instant.tzinfo is UTC


def test_the_two_conversions_are_inverse() -> None:
    assert micros_to_instant(instant_to_micros(_INSTANT)) == _INSTANT
    assert instant_to_micros(micros_to_instant(_MICROS)) == _MICROS


def test_iso_to_micros_reads_a_stamp_with_a_fraction(connection: sqlite3.Connection) -> None:
    assert _iso_to_micros(connection, "2026-06-11T12:00:00.123456+00:00") == _MICROS


def test_iso_to_micros_reads_a_stamp_without_a_fraction(connection: sqlite3.Connection) -> None:
    assert _iso_to_micros(connection, "2026-06-11T12:00:00+00:00") == _MICROS - 123456


def test_iso_to_micros_normalizes_an_offset_to_utc(connection: sqlite3.Connection) -> None:
    assert _iso_to_micros(connection, "2026-06-11T14:00:00.123456+02:00") == _MICROS


def test_iso_to_micros_refuses_a_naive_stamp(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.OperationalError, match="user-defined function raised exception"):
        _iso_to_micros(connection, "2026-06-11T12:00:00.123456")
