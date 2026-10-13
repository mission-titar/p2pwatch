"""``SqliteSourceRepository``: this node's source points in the catalog (source points, D4, D5)."""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import suppress
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
    source_tolerance,
)
from p2pwatch.ports.source_repository import EarlierPoints, RecordedReading

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# The source's latest point before the read, within the tolerance. Without an identity, a source
# is its name among the variants without one (D4). One seek per variant, never a walk of the points.
# The unary + keeps the planner off idx_source_variants_node_id, which holds all this node's rows.
_LATEST_POINT = """
SELECT v.role, o.transfer_counter
FROM source_variants AS v
INNER JOIN source_observations AS o ON v.variant_id = o.variant_id
WHERE
    v.file_id = :file_id
    AND v.source_id IS :source_id
    AND (:source_id IS NOT NULL OR v.name = :name)
    AND +v.node_id = :node_id
    AND o.observed_at = (
        SELECT MAX(p.observed_at) FROM source_observations AS p
        WHERE p.variant_id = v.variant_id AND p.observed_at >= :since AND p.observed_at < :read_at
    )
ORDER BY o.observed_at DESC
LIMIT 1
"""

_INSERT_SOURCE = """
INSERT INTO sources (source_id, network, native_id) VALUES (?, ?, ?)
ON CONFLICT DO NOTHING
"""

_INSERT_VARIANT = """
INSERT INTO source_variants (
    file_id, source_id, name, software, role, contact_point, directly_reachable, raw_meta,
    node_id, content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (content_hash) DO NOTHING
"""

# Not OR IGNORE, which would also swallow the counter's CHECK (D2).
_INSERT_POINT = """
INSERT INTO source_observations (variant_id, observed_at, transfer_counter)
SELECT variant_id, ?, ? FROM source_variants WHERE content_hash = ?
ON CONFLICT (variant_id, observed_at) DO NOTHING
"""

# Each variant's latest point before the round, one seek each (D5's reason); + as in _LATEST_POINT.
_EARLIER_POINTS = """
SELECT
    v.role,
    (
        SELECT MAX(o.observed_at) FROM source_observations AS o
        WHERE o.variant_id = v.variant_id AND o.observed_at < ?
    )
FROM source_variants AS v
WHERE v.source_id = ? AND +v.node_id = ?
"""

_HAS_POINTS_BEFORE = """
SELECT EXISTS (
    SELECT 1 FROM source_variants AS v
    INNER JOIN source_observations AS o ON v.variant_id = o.variant_id
    WHERE v.node_id = ? AND o.observed_at < ?
)
"""


class SqliteSourceRepository:
    """SQLite implementation of the ``SourceRepository`` port (STRUCTURAL satisfaction).

    ``spacing`` is the longest time between two reads of the sources (D3)."""

    def __init__(self, connection: sqlite3.Connection, node_id: str, spacing: timedelta) -> None:
        self._connection = connection
        self._node_id = node_id
        self._tolerance = source_tolerance(spacing) // _MICROSECOND

    def record_readings(
        self, file: FileKey, readings: Sequence[SourceReading], read_at: datetime
    ) -> tuple[RecordedReading, ...]:
        """ONE transaction; each reading kept, with its role, a carried one included."""
        for reading in readings:
            point = reading.contact_point
            if point is not None and not is_contact_point(file.network, point):
                raise PersistenceError(f"not a {file.network} contact point: {point!r}")
        now = _micros(read_at)
        recorded: list[RecordedReading] = []
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for reading in readings:
                    if reading.key is None and reading.name is None:
                        continue  # nothing could tell it from the next one (D4)
                    role = self._record(file, reading, now)
                    recorded.append(RecordedReading(reading.key, reading.name, role))
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
        return tuple(recorded)

    def _record(self, file: FileKey, reading: SourceReading, now: int) -> SourceRole:
        """Writes the reading's variant and point; its role, a carried one included."""
        role = reading.role
        if role is None:
            role = carried_role(self._carried_from(file, reading, now))
        variant = _variant(file, reading, role, self._node_id)
        key = _content_hash(variant)
        if reading.key is not None:
            source = reading.key
            self._connection.execute(
                _INSERT_SOURCE, (source.source_id, source.network, source.native_id)
            )
        self._connection.execute(_INSERT_VARIANT, (*variant, key))
        self._connection.execute(_INSERT_POINT, (now, reading.transfer_counter, key))
        return role

    def _carried_from(self, file: FileKey, reading: SourceReading, now: int) -> SourceRole | None:
        """The role of the latest point, unless aMule recreated the client since (its counter)."""
        row = self._connection.execute(
            _LATEST_POINT,
            {
                "file_id": file.file_id,
                "source_id": None if reading.key is None else reading.key.source_id,
                "name": reading.name,
                "node_id": self._node_id,
                "since": now - self._tolerance,
                "read_at": now,
            },
        ).fetchone()
        if row is None or row[1] > reading.transfer_counter:
            return None
        return SourceRole(row[0])

    def earlier_points(self, source: SourceKey, before: datetime) -> EarlierPoints:
        """Whether a useful point exists, and the latest useful or not-useful one."""
        with wrap_sqlite_errors():
            rows = self._connection.execute(
                _EARLIER_POINTS, (_micros(before), source.source_id, self._node_id)
            ).fetchall()
        seen = [(SourceRole(role).group, latest) for role, latest in rows if latest is not None]
        known = [latest for group, latest in seen if group is not SourceGroup.UNKNOWN]
        return EarlierPoints(
            useful=any(group is SourceGroup.USEFUL for group, _ in seen),
            last_known_at=_EPOCH + max(known) * _MICROSECOND if known else None,
        )

    def has_points_before(self, before: datetime) -> bool:
        """Whether this node has a point observed before ``before``."""
        with wrap_sqlite_errors():
            row = self._connection.execute(
                _HAS_POINTS_BEFORE, (self._node_id, _micros(before))
            ).fetchone()
        return bool(row[0])


def _micros(moment: datetime) -> int:
    return iso_to_micros(utc_iso(moment))


def _variant(
    file: FileKey, reading: SourceReading, role: SourceRole, node_id: str
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
        node_id,
    )


def _content_hash(variant: tuple[bytes | str | bool | None, ...]) -> bytes:
    """blake2b-128 of the columns as compact JSON, a BLOB written as lowercase hex."""
    columns = [value.hex() if isinstance(value, bytes) else value for value in variant]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=16).digest()
