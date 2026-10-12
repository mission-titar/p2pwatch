"""``SqliteSourceRepository``: this node's source ranges in the catalog (stage 4 spec, D4, D9)."""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.persistence_sqlite.errors import PersistenceError, wrap_sqlite_errors
from p2pwatch.adapters.persistence_sqlite.variants import iso_to_micros
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import (
    SourceGroup,
    SourceKey,
    SourceReading,
    SourceRole,
    carried_role,
    is_contact_point,
)
from p2pwatch.ports.source_repository import EarlierRanges, OpenedRange

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# Without an identity, a source is its name among the variants without one (D4).
_LATEST_RANGE = """
SELECT
    r.variant_id, r.first_seen_at, r.last_seen_at, r.received_bytes, r.transfer_counter,
    v.role, v.content_hash
FROM source_variants AS v
INNER JOIN source_ranges AS r ON v.variant_id = r.variant_id
WHERE
    v.file_id = :file_id
    AND v.source_id IS :source_id
    AND (:source_id IS NOT NULL OR v.name = :name)
    AND r.node_id = :node_id
ORDER BY r.first_seen_at DESC
LIMIT 1
"""

_INSERT_SOURCE = """
INSERT INTO sources (source_id, network, native_id) VALUES (?, ?, ?)
ON CONFLICT DO NOTHING
"""

_INSERT_VARIANT = """
INSERT INTO source_variants (
    file_id, source_id, name, software, role, contact_point, directly_reachable, raw_meta,
    content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (content_hash) DO NOTHING
"""

_OPEN_RANGE = """
INSERT INTO source_ranges (
    variant_id, node_id, first_seen_at, last_seen_at, received_bytes, transfer_counter
)
SELECT variant_id, ?, ?, ?, 0, ? FROM source_variants WHERE content_hash = ?
"""

_EXTEND_RANGE = """
UPDATE source_ranges SET last_seen_at = ?, received_bytes = ?, transfer_counter = ?
WHERE variant_id = ? AND node_id = ? AND first_seen_at = ?
"""

_EARLIER_RANGES = """
SELECT v.role, MAX(r.last_seen_at)
FROM source_variants AS v
INNER JOIN source_ranges AS r ON v.variant_id = r.variant_id
WHERE v.source_id = ? AND r.node_id = ? AND r.first_seen_at < ?
GROUP BY v.role
"""

_HAS_RANGES_BEFORE = """
SELECT EXISTS (SELECT 1 FROM source_ranges WHERE node_id = ? AND first_seen_at < ?)
"""


@dataclass(frozen=True)
class _Range:
    variant_id: int
    first_seen_at: int
    last_seen_at: int
    received_bytes: int
    transfer_counter: int
    role: SourceRole
    content_hash: bytes


class SqliteSourceRepository:
    """SQLite implementation of the ``SourceRepository`` port (STRUCTURAL satisfaction)."""

    def __init__(self, connection: sqlite3.Connection, node_id: str) -> None:
        self._connection = connection
        self._node_id = node_id

    def record_readings(
        self,
        file: FileKey,
        readings: Sequence[SourceReading],
        read_at: datetime,
        tolerance: timedelta,
    ) -> tuple[OpenedRange, ...]:
        """ONE transaction; the ranges it opened, each with its role, a carried one included."""
        for reading in readings:
            point = reading.contact_point
            if point is not None and not is_contact_point(file.network, point):
                raise PersistenceError(f"not a {file.network} contact point: {point!r}")
        now = _micros(read_at)
        opened: list[OpenedRange] = []
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for reading in readings:
                    role = self._record(file, reading, now, tolerance // _MICROSECOND)
                    if role is not None:
                        opened.append(OpenedRange(reading.key, reading.name, role))
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
        return tuple(opened)

    def _record(
        self, file: FileKey, reading: SourceReading, now: int, tolerance: int
    ) -> SourceRole | None:
        """Extends or opens the reading's range; the role of a range it opened, else ``None``."""
        if reading.key is None and reading.name is None:
            return None
        latest = self._latest_range(file, reading)
        if latest is not None and now <= latest.last_seen_at:
            return None  # the clock stepped back, or a second reading of one identity
        if latest is not None and (
            now > latest.last_seen_at + tolerance
            or reading.transfer_counter < latest.transfer_counter
        ):
            latest = None  # a missed round too many, or aMule recreated the client
        role = reading.role
        if role is None:
            role = carried_role(None if latest is None else latest.role)
        variant = _variant(file, reading, role)
        key = _content_hash(variant)
        if latest is not None and latest.content_hash == key:
            growth = reading.transfer_counter - latest.transfer_counter
            received = latest.received_bytes + (growth if role is SourceRole.SENDING else 0)
            self._connection.execute(
                _EXTEND_RANGE,
                (
                    now,
                    received,
                    reading.transfer_counter,
                    latest.variant_id,
                    self._node_id,
                    latest.first_seen_at,
                ),
            )
            return None
        if reading.key is not None:
            source = reading.key
            self._connection.execute(
                _INSERT_SOURCE, (source.source_id, source.network, source.native_id)
            )
        self._connection.execute(_INSERT_VARIANT, (*variant, key))
        self._connection.execute(
            _OPEN_RANGE, (self._node_id, now, now, reading.transfer_counter, key)
        )
        return role

    def _latest_range(self, file: FileKey, reading: SourceReading) -> _Range | None:
        row = self._connection.execute(
            _LATEST_RANGE,
            {
                "file_id": file.file_id,
                "source_id": None if reading.key is None else reading.key.source_id,
                "name": reading.name,
                "node_id": self._node_id,
            },
        ).fetchone()
        if row is None:
            return None
        return _Range(row[0], row[1], row[2], row[3], row[4], SourceRole(row[5]), row[6])

    def earlier_ranges(self, source: SourceKey, started_before: datetime) -> EarlierRanges:
        """Whether a useful range exists, and the end of the latest useful or not-useful one."""
        with wrap_sqlite_errors():
            rows = self._connection.execute(
                _EARLIER_RANGES, (source.source_id, self._node_id, _micros(started_before))
            ).fetchall()
        groups = [(SourceRole(role).group, last_seen_at) for role, last_seen_at in rows]
        known = [end for group, end in groups if group is not SourceGroup.UNKNOWN]
        return EarlierRanges(
            useful=any(group is SourceGroup.USEFUL for group, _ in groups),
            last_known_at=_EPOCH + max(known) * _MICROSECOND if known else None,
        )

    def has_ranges_before(self, started_before: datetime) -> bool:
        """Whether this node has a range that started before ``started_before``."""
        with wrap_sqlite_errors():
            row = self._connection.execute(
                _HAS_RANGES_BEFORE, (self._node_id, _micros(started_before))
            ).fetchone()
        return bool(row[0])


def _micros(moment: datetime) -> int:
    return iso_to_micros(utc_iso(moment))


def _variant(
    file: FileKey, reading: SourceReading, role: SourceRole
) -> tuple[bytes | str | bool | None, ...]:
    """The variant's columns in the table's order, ``raw_meta`` a JSON object with sorted keys."""
    return (
        file.file_id,
        None if reading.key is None else reading.key.source_id,
        reading.name,
        reading.software,
        role.value,
        reading.contact_point,
        reading.directly_reachable,
        json.dumps(dict(reading.raw_meta), ensure_ascii=False, sort_keys=True),
    )


def _content_hash(variant: tuple[bytes | str | bool | None, ...]) -> bytes:
    """blake2b-128 of the columns as compact JSON, a BLOB written as lowercase hex."""
    columns = [value.hex() if isinstance(value, bytes) else value for value in variant]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=16).digest()
