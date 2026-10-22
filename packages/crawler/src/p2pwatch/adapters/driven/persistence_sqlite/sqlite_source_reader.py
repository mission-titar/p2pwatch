"""Read-only reads of the catalog (webui spec W-D6 / §6).

``SqliteSourceReader`` reads the sources with a user hash, last seen first, and how many match
the search; a source's history and a source name's; and a file's sharing periods in a window,
newest first.

All SQL lives in module constants, parameterized (no value interpolation).
"""

import sqlite3
from datetime import UTC, datetime, timedelta

from p2pwatch.adapters.driven.persistence_sqlite.observation_read import best_observation
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey, SourceRole
from p2pwatch.domain.source_history import SourceHistory, SourceNameHistory, SourceNaming

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# A period joins the consecutive points of one identity (the source_id, else the name) on one
# file and one node, cut where the variant changes, a gap passes the window's gap or the
# session's received bytes drop (source points spec, D6). Only the window's points are read, a
# seek on the primary key bounded by ``observed_at``. A ``_WHERE_*`` goes between this and
# ``_SQL_PERIODS_END``.
_SQL_PERIODS = """\
WITH points AS (
    SELECT
        o.variant_id,
        o.observed_at,
        o.session_received_bytes,
        v.file_id,
        v.node_id,
        v.source_id,
        IIF(v.source_id IS NULL, v.name, NULL) AS hashless_name
    FROM source_variants AS v
    JOIN source_observations AS o ON o.variant_id = v.variant_id
"""
_SQL_PERIODS_END = """\
        AND o.observed_at >= :since AND o.observed_at < :until
),
starts AS (
    SELECT
        *,
        (
            variant_id IS NOT LAG(variant_id) OVER identity
            OR observed_at - LAG(observed_at) OVER identity > :gap
            OR session_received_bytes < LAG(session_received_bytes) OVER identity
        ) AS starts_period
    FROM points
    WINDOW identity AS (
        PARTITION BY file_id, node_id, source_id, hashless_name
        ORDER BY observed_at, variant_id
    )
),
numbered AS (
    SELECT
        variant_id,
        observed_at,
        session_received_bytes,
        SUM(starts_period) OVER (
            PARTITION BY file_id, node_id, source_id, hashless_name
            ORDER BY observed_at, variant_id
            ROWS UNBOUNDED PRECEDING
        ) AS period
    FROM starts
),
periods AS (
    SELECT
        variant_id,
        MIN(observed_at) AS first_seen_at,
        MAX(observed_at) AS last_seen_at,
        MAX(session_received_bytes) - MIN(session_received_bytes) AS growth
    FROM numbered
    GROUP BY variant_id, period
)
SELECT
    f.network AS file_network,
    f.native_id AS file_native_id,
    s.network,
    s.native_id,
    v.name,
    v.role,
    v.contact_point,
    v.connectable,
    p.first_seen_at,
    p.last_seen_at,
    p.growth,
    v.node_id
FROM periods AS p
JOIN source_variants AS v ON v.variant_id = p.variant_id
JOIN files AS f ON f.file_id = v.file_id
LEFT JOIN sources AS s ON s.source_id = v.source_id
ORDER BY p.first_seen_at DESC, p.variant_id DESC
"""

# A variant's latest point, one seek on the primary key, never an aggregate of every point.
_SQL_VARIANT_LAST_SEEN = (
    "(SELECT MAX(o.observed_at) FROM source_observations AS o WHERE o.variant_id = v.variant_id)"
)

# The sources with a user hash, each with its last read and its number of files (D13). A source
# without a hash has no ``sources`` row, so it is not listed.
_SQL_SOURCES_FROM = f"""\
FROM sources AS s
JOIN (
    SELECT
        v.source_id,
        MAX({_SQL_VARIANT_LAST_SEEN}) AS latest_seen_at,
        COUNT(DISTINCT v.file_id) AS file_count
    FROM source_variants AS v
    GROUP BY v.source_id
) AS seen ON seen.source_id = s.source_id
"""

# A hash prefix, or a substring of any name the source carried; LIKE ignores ASCII case.
_SQL_SOURCES_SEARCH = """\
WHERE s.native_id LIKE ? OR EXISTS (
    SELECT 1 FROM source_variants AS nv WHERE nv.source_id = s.source_id AND nv.name LIKE ?
)
"""

# The latest name is its named variant with the latest point: a reading without a name says
# nothing about the name.
_SQL_LIST_SOURCES_SELECT = f"""\
SELECT
    s.network,
    s.native_id,
    seen.latest_seen_at,
    seen.file_count,
    (
        SELECT v.name
        FROM source_variants AS v
        WHERE v.source_id = s.source_id AND v.name IS NOT NULL
        ORDER BY {_SQL_VARIANT_LAST_SEEN} DESC, v.variant_id DESC
        LIMIT 1
    ) AS name
"""

_SQL_SOURCE = "SELECT network, native_id FROM sources WHERE source_id = ?"
_SQL_NAME_EXISTS = "SELECT 1 FROM source_variants WHERE name = ? LIMIT 1"

# One row per (source, name) pair: a source's names, or a name's sources (D13). The WHERE that
# picks one side goes between this and ``_SQL_PAIRS_END``.
_SQL_PAIRS = f"""\
SELECT
    s.network,
    s.native_id,
    v.name,
    MAX({_SQL_VARIANT_LAST_SEEN}) AS latest_seen_at,
    COUNT(DISTINCT v.file_id) AS file_count
FROM source_variants AS v
JOIN sources AS s ON s.source_id = v.source_id
"""
_SQL_PAIRS_END = """\
GROUP BY v.source_id, v.name
ORDER BY latest_seen_at DESC, v.source_id, v.name
LIMIT :limit OFFSET :offset
"""

# The WHERE of each read: a hash page lists names and a name page hashes, nothing further.
_WHERE_FILE = "WHERE v.file_id = :key\n"
_WHERE_SOURCE = "WHERE v.source_id = :key\n"
_WHERE_SOURCE_NAMED = "WHERE v.source_id = :key AND v.name IS NOT NULL\n"
_WHERE_NAME = "WHERE v.name = :key\n"
_WHERE_NAME_HASHLESS = "WHERE v.name = :key AND v.source_id IS NULL\n"


def _sources_search(search_text: str | None) -> tuple[str, list[str]]:
    """The sources list's search clause and its parameters; none without a search text."""
    if search_text is None:
        return "", []
    return _SQL_SOURCES_SEARCH, [f"{search_text}%", f"%{search_text}%"]


def _micros(moment: datetime) -> int:
    return (moment - _EPOCH) // _MICROSECOND


def _sharing_period(row: sqlite3.Row) -> SharingPeriod:
    """A row of ``_SQL_PERIODS`` as a period; only a sending one received its growth (D6)."""
    network, connectable = row["network"], row["connectable"]
    role = SourceRole(row["role"])
    return SharingPeriod(
        file=FileKey(Network(row["file_network"]), row["file_native_id"]),
        source=None if network is None else SourceKey(Network(network), row["native_id"]),
        source_name=row["name"],
        role=role,
        contact_point=row["contact_point"],
        connectable=None if connectable is None else bool(connectable),
        first_seen_at=_EPOCH + row["first_seen_at"] * _MICROSECOND,
        last_seen_at=_EPOCH + row["last_seen_at"] * _MICROSECOND,
        received_bytes=row["growth"] if role is SourceRole.SENDING else 0,
        node_id=row["node_id"],
    )


def _period_rows(
    connection: sqlite3.Connection, where: str, key: bytes | str, window: PeriodWindow
) -> list[sqlite3.Row]:
    params = {
        "key": key,
        "since": _micros(window.since),
        "until": _micros(window.until),
        "gap": window.gap // _MICROSECOND,
    }
    return connection.execute(_SQL_PERIODS + where + _SQL_PERIODS_END, params).fetchall()


def _source_namings(
    connection: sqlite3.Connection, where: str, key: bytes | str, limit: int, offset: int
) -> tuple[SourceNaming, ...]:
    params = {"key": key, "limit": limit, "offset": offset}
    return tuple(
        SourceNaming(
            source=SourceKey(Network(row["network"]), row["native_id"]),
            source_name=row["name"],
            latest_seen_at=_EPOCH + row["latest_seen_at"] * _MICROSECOND,
            file_count=row["file_count"],
        )
        for row in connection.execute(_SQL_PAIRS + where + _SQL_PAIRS_END, params)
    )


def _best_filename_by_file(
    connection: sqlite3.Connection, sharing_periods: tuple[SharingPeriod, ...]
) -> dict[FileKey, str]:
    """The best filename of each file of ``sharing_periods`` ever seen."""
    best_filename_by_file = {}
    for file in {period.file for period in sharing_periods}:
        best = best_observation(connection, file)
        if best is not None:
            best_filename_by_file[file] = best.reported_file.filename
    return best_filename_by_file


class SqliteSourceReader(SourceReader):
    """Reads through the calling thread's read-only connection."""

    def __init__(self, reader_provider: ThreadReadConnections) -> None:
        self._reader_provider = reader_provider

    def read_known_sources(
        self, *, search_text: str | None, limit: int, offset: int
    ) -> tuple[KnownSource, ...]:
        search, params = _sources_search(search_text)
        sql = (
            _SQL_LIST_SOURCES_SELECT
            + _SQL_SOURCES_FROM
            + search
            + "ORDER BY seen.latest_seen_at DESC, s.source_id\nLIMIT ? OFFSET ?\n"
        )
        rows = self._reader_provider.connection().execute(sql, [*params, limit, offset])
        return tuple(
            KnownSource(
                source=SourceKey(Network(row["network"]), row["native_id"]),
                source_name=row["name"],
                latest_seen_at=_EPOCH + row["latest_seen_at"] * _MICROSECOND,
                file_count=row["file_count"],
            )
            for row in rows
        )

    def read_source_count(self, *, search_text: str | None) -> int:
        search, params = _sources_search(search_text)
        sql = "SELECT COUNT(*) AS n\n" + _SQL_SOURCES_FROM + search
        count: int = self._reader_provider.connection().execute(sql, params).fetchone()["n"]
        return count

    def read_source_history(
        self, source_id: bytes, *, limit: int, offset: int, window: PeriodWindow
    ) -> SourceHistory | None:
        connection = self._reader_provider.connection()
        row = connection.execute(_SQL_SOURCE, (source_id,)).fetchone()
        if row is None:
            return None
        sharing_periods = tuple(
            map(_sharing_period, _period_rows(connection, _WHERE_SOURCE, source_id, window))
        )
        return SourceHistory(
            source=SourceKey(Network(row["network"]), row["native_id"]),
            source_namings=_source_namings(
                connection, _WHERE_SOURCE_NAMED, source_id, limit, offset
            ),
            sharing_periods=sharing_periods,
            best_filename_by_file=_best_filename_by_file(connection, sharing_periods),
        )

    def read_source_name_history(
        self, source_name: str, *, limit: int, offset: int, window: PeriodWindow
    ) -> SourceNameHistory | None:
        connection = self._reader_provider.connection()
        if connection.execute(_SQL_NAME_EXISTS, (source_name,)).fetchone() is None:
            return None
        sharing_periods = tuple(
            map(
                _sharing_period,
                _period_rows(connection, _WHERE_NAME_HASHLESS, source_name, window),
            )
        )
        return SourceNameHistory(
            source_name=source_name,
            source_namings=_source_namings(connection, _WHERE_NAME, source_name, limit, offset),
            sharing_periods=sharing_periods,
            best_filename_by_file=_best_filename_by_file(connection, sharing_periods),
        )

    def read_sharing_periods(
        self, file: FileKey, window: PeriodWindow
    ) -> tuple[SharingPeriod, ...]:
        connection = self._reader_provider.connection()
        return tuple(
            map(_sharing_period, _period_rows(connection, _WHERE_FILE, file.file_id, window))
        )
