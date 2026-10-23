"""``SqliteSourcePointStore``: each node's source points in the catalog (source points, D4, D5)."""

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.driven.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.driven.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.adapters.driven.persistence_sqlite.variants import iso_to_micros
from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import LatestPoint, SourceKey, SourcePoint, SourceReading, SourceRole

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# The source's latest point in the window. Without an identity, a source is its name among the
# variants without one (D4). One seek per variant, never a walk of the points.
# The unary + keeps the planner off idx_source_variants_node_id, which holds all this node's rows.
_LATEST_POINT = """
SELECT v.role, o.observed_at, o.session_received_bytes
FROM source_variants AS v
INNER JOIN source_observations AS o ON v.variant_id = o.variant_id
WHERE
    v.file_id = :file_id
    AND v.source_id IS :source_id
    AND (:source_id IS NOT NULL OR v.name = :source_name)
    AND +v.node_id = :node_id
    AND o.observed_at = (
        SELECT MAX(p.observed_at) FROM source_observations AS p
        WHERE p.variant_id = v.variant_id AND p.observed_at >= :since AND p.observed_at < :before
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
    file_id, source_id, name, software, role, contact_point, connectable, raw_metadata,
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
SELECT v.role, o.observed_at, o.session_received_bytes
FROM source_variants AS v
INNER JOIN source_observations AS o ON v.variant_id = o.variant_id
WHERE
    v.source_id = :source_id
    AND +v.node_id = :node_id
    AND o.observed_at = (
        SELECT MAX(p.observed_at) FROM source_observations AS p
        WHERE p.variant_id = v.variant_id AND p.observed_at < :before
    )
"""

_HAS_POINTS_BEFORE = """
SELECT EXISTS (
    SELECT 1 FROM source_variants AS v
    INNER JOIN source_observations AS o ON v.variant_id = o.variant_id
    WHERE v.node_id = ? AND o.observed_at < ?
)
"""


class SqliteSourcePointStore(SourcePointWriter, SourcePointReader):
    """SQLite implementation of the source points' ports."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_points(self, points: Sequence[SourcePoint]) -> None:
        """ONE transaction."""
        with wrap_sqlite_errors():
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for point in points:
                    self._record(point)
                self._connection.execute("COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise

    def _record(self, point: SourcePoint) -> None:
        """Writes the point's variant and the point."""
        reading = point.reading
        variant = _variant_columns(point)
        variant_content_hash = _content_hash(variant)
        if reading.source is not None:
            source = reading.source
            self._connection.execute(
                _INSERT_SOURCE, (source.source_id, source.network, source.native_id)
            )
        self._connection.execute(_INSERT_VARIANT, (*variant, variant_content_hash))
        self._connection.execute(
            _INSERT_POINT,
            (_micros(point.observed_at), reading.session_received_bytes, variant_content_hash),
        )

    def read_latest_point(
        self,
        file: FileKey,
        reading: SourceReading,
        since: datetime,
        before: datetime,
        node_id: str,
    ) -> LatestPoint | None:
        """The latest point of ``reading``'s source on ``file`` from ``since`` to ``before``."""
        with wrap_sqlite_errors():
            row = self._connection.execute(
                _LATEST_POINT,
                {
                    "file_id": file.file_id,
                    "source_id": None if reading.source is None else reading.source.source_id,
                    "source_name": reading.source_name,
                    "node_id": node_id,
                    "since": _micros(since),
                    "before": _micros(before),
                },
            ).fetchone()
        return None if row is None else _latest_point(*row)

    def read_earlier_points(
        self, source: SourceKey, before: datetime, node_id: str
    ) -> tuple[LatestPoint, ...]:
        """The latest point of each of ``source``'s variants that has one before ``before``."""
        with wrap_sqlite_errors():
            rows = self._connection.execute(
                _EARLIER_POINTS,
                {"source_id": source.source_id, "node_id": node_id, "before": _micros(before)},
            ).fetchall()
        return tuple(_latest_point(*row) for row in rows)

    def has_points_before(self, before: datetime, node_id: str) -> bool:
        """Whether ``node_id`` has a point observed before ``before``."""
        with wrap_sqlite_errors():
            row = self._connection.execute(
                _HAS_POINTS_BEFORE, (node_id, _micros(before))
            ).fetchone()
        return bool(row[0])


def _micros(moment: datetime) -> int:
    return iso_to_micros(utc_iso(moment))


def _latest_point(role: str, observed_at: int, session_received_bytes: int) -> LatestPoint:
    return LatestPoint(
        SourceRole(role), _EPOCH + observed_at * _MICROSECOND, session_received_bytes
    )


def _variant_columns(point: SourcePoint) -> tuple[bytes | str | bool | None, ...]:
    """The variant's columns in table order, ``raw_metadata`` a JSON object with sorted keys."""
    reading = point.reading
    return (
        point.file.file_id,
        None if reading.source is None else reading.source.source_id,
        reading.source_name,
        reading.software,
        point.role.value,
        None if reading.contact_point is None else reading.contact_point.server,
        reading.connectable,
        json.dumps(dict(reading.raw_metadata), ensure_ascii=False, sort_keys=True),
        point.node_id,
    )


def _content_hash(variant: tuple[bytes | str | bool | None, ...]) -> bytes:
    """blake2b-128 of the columns as compact JSON, a BLOB written as lowercase hex."""
    columns = [column.hex() if isinstance(column, bytes) else column for column in variant]
    canonical = json.dumps(columns, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(canonical.encode(), digest_size=16).digest()
