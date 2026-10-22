"""``SqliteSourcePointStore``: each node's source points in the catalog (source points, D4, D5)."""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import PersistenceError, wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.variants import iso_to_micros
from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import (
    EarlierPoints,
    RecordedReading,
    SourceKey,
    SourceReading,
    SourceRole,
    SourceUsefulness,
    carried_role,
    carried_role_max_age,
    is_contact_point,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# The source's latest point before the read, within the carried role's max age. Without an
# identity, a source is its name among the variants without one (D4). One seek per variant, never a
# walk of the points.
# The unary + keeps the planner off idx_source_variants_node_id, which holds all this node's rows.
_LATEST_POINT = """
SELECT v.role, o.session_received_bytes
FROM source_variants AS v
INNER JOIN source_observations AS o ON v.variant_id = o.variant_id
WHERE
    v.file_id = :file_id
    AND v.source_id IS :source_id
    AND (:source_id IS NOT NULL OR v.name = :source_name)
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
    file_id, source_id, name, software, role, contact_point, connectable, raw_meta,
    node_id, content_hash
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (content_hash) DO NOTHING
"""

# Not OR IGNORE, which would also swallow the CHECK on session_received_bytes (D2).
_INSERT_POINT = """
INSERT INTO source_observations (variant_id, observed_at, session_received_bytes)
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


class SqliteSourcePointStore(SourcePointWriter, SourcePointReader):
    """SQLite implementation of the source points' ports.

    ``time_between_reads`` is what the carried role's max age assumes (D3)."""

    def __init__(self, connection: sqlite3.Connection, time_between_reads: timedelta) -> None:
        self._connection = connection
        self._carried_role_max_age_micros = carried_role_max_age(time_between_reads) // _MICROSECOND

    def record_readings(
        self, file: FileKey, readings: Sequence[SourceReading], read_at: datetime, node_id: str
    ) -> tuple[RecordedReading, ...]:
        """ONE transaction; each reading kept, with its role, a carried one included."""
        for reading in readings:
            contact_point = reading.contact_point
            if contact_point is not None and not is_contact_point(file.network, contact_point):
                raise PersistenceError(f"not a {file.network} contact point: {contact_point!r}")
        read_at_micros = _micros(read_at)
        recorded: list[RecordedReading] = []
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for reading in readings:
                    if reading.source is None and reading.source_name is None:
                        continue  # nothing could tell it from the next one (D4)
                    role = self._record(file, reading, read_at_micros, node_id)
                    recorded.append(RecordedReading(reading.source, reading.source_name, role))
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
        return tuple(recorded)

    def _record(
        self, file: FileKey, reading: SourceReading, read_at_micros: int, node_id: str
    ) -> SourceRole:
        """Writes the reading's variant and point; its role, a carried one included."""
        role = reading.role
        if role is None:
            role = carried_role(self._latest_point_role(file, reading, read_at_micros, node_id))
        variant = _variant_columns(file, reading, role, node_id)
        variant_content_hash = _content_hash(variant)
        if reading.source is not None:
            source = reading.source
            self._connection.execute(
                _INSERT_SOURCE, (source.source_id, source.network, source.native_id)
            )
        self._connection.execute(_INSERT_VARIANT, (*variant, variant_content_hash))
        self._connection.execute(
            _INSERT_POINT, (read_at_micros, reading.session_received_bytes, variant_content_hash)
        )
        return role

    def _latest_point_role(
        self, file: FileKey, reading: SourceReading, read_at_micros: int, node_id: str
    ) -> SourceRole | None:
        """The role of the latest point, unless aMule recreated the client since (its session's
        received bytes dropped)."""
        row = self._connection.execute(
            _LATEST_POINT,
            {
                "file_id": file.file_id,
                "source_id": None if reading.source is None else reading.source.source_id,
                "source_name": reading.source_name,
                "node_id": node_id,
                "since": read_at_micros - self._carried_role_max_age_micros,
                "read_at": read_at_micros,
            },
        ).fetchone()
        if row is None or row[1] > reading.session_received_bytes:
            return None
        return SourceRole(row[0])

    def read_earlier_points(
        self, source: SourceKey, before: datetime, node_id: str
    ) -> EarlierPoints:
        """Whether a useful point exists, and the latest useful or not-useful one."""
        with wrap_sqlite_errors():
            rows = self._connection.execute(
                _EARLIER_POINTS, (_micros(before), source.source_id, node_id)
            ).fetchall()
        seen = [
            (SourceRole(role).usefulness, latest) for role, latest in rows if latest is not None
        ]
        known = [
            latest for usefulness, latest in seen if usefulness is not SourceUsefulness.UNKNOWN
        ]
        return EarlierPoints(
            has_useful_point=any(usefulness is SourceUsefulness.USEFUL for usefulness, _ in seen),
            latest_known_at=_EPOCH + max(known) * _MICROSECOND if known else None,
        )

    def has_points_before(self, before: datetime, node_id: str) -> bool:
        """Whether ``node_id`` has a point observed before ``before``."""
        with wrap_sqlite_errors():
            row = self._connection.execute(
                _HAS_POINTS_BEFORE, (node_id, _micros(before))
            ).fetchone()
        return bool(row[0])


def _micros(moment: datetime) -> int:
    return iso_to_micros(utc_iso(moment))


def _variant_columns(
    file: FileKey, reading: SourceReading, role: SourceRole, node_id: str
) -> tuple[bytes | str | bool | None, ...]:
    """The variant's columns in the table's order, ``raw_meta`` a JSON object with sorted keys."""
    return (
        file.file_id,
        None if reading.source is None else reading.source.source_id,
        reading.source_name,
        reading.software,
        role.value,
        reading.contact_point,
        reading.connectable,
        json.dumps(dict(reading.raw_meta), ensure_ascii=False, sort_keys=True),
        node_id,
    )


def _content_hash(variant: tuple[bytes | str | bool | None, ...]) -> bytes:
    """blake2b-128 of the columns as compact JSON, a BLOB written as lowercase hex."""
    columns = [value.hex() if isinstance(value, bytes) else value for value in variant]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=16).digest()
