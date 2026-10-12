"""``SqliteSourceRepository``: this node's source ranges in the catalog (stage 4 spec, D9)."""

import sqlite3
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.persistence_sqlite.connection import utc_iso
from p2pwatch.adapters.persistence_sqlite.errors import wrap_sqlite_errors
from p2pwatch.adapters.persistence_sqlite.variants import iso_to_micros
from p2pwatch.domain.source import SourceGroup, SourceKey, SourceRole
from p2pwatch.ports.source_repository import EarlierRanges

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

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


class SqliteSourceRepository:
    """SQLite implementation of the ``SourceRepository`` port (STRUCTURAL satisfaction)."""

    def __init__(self, connection: sqlite3.Connection, node_id: str) -> None:
        self._connection = connection
        self._node_id = node_id

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
