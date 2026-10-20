"""Read-only reads of the catalog (webui spec W-D6 / §6).

``SqliteCoverageReader.read_target_coverage()``: per ``target_id``, the tier of each file's
LATEST match decision **per target** (ROW_NUMBER window PARTITION BY ``(file_id, target_id)``),
so a whole-episode file contributes to every target it matches. The legacy ``target_id=''``
sentinel and per-target ``retracted`` rows are excluded.

``SqliteCatalogFileReader`` reads the files page: its entries (files ⨝ latest observation ⨝
current decisions, optional filters + LIMIT/OFFSET), their ``(matched, total)`` counts and their
tier facet; and a file's history: its observations in an interval, its latest one, its known names
and its current decisions, ``None`` if the file is unknown.

``SqliteSourceReader`` reads the sources with a user hash, last seen first, and how many match
the search; a source's history and a source name's; and a file's sharing periods in a window,
newest first.

All SQL lives in module constants, parameterized (no value interpolation).
"""

import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from catalog_matching.domain.config import TIER_RANK
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.adapters.driven.persistence_sqlite.observation_read import (
    LATEST_OBSERVATION_CTE,
    best_observation,
    known_filenames,
    latest_observation,
    observation_from_row,
    observations_between,
)
from p2pwatch.adapters.driven.persistence_sqlite.reader import ReaderProvider
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import DatedDecision, FileHistory
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey, SourceRole
from p2pwatch.domain.source_history import SourceHistory, SourceNameHistory, SourceNaming
from p2pwatch.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.ports.driven.coverage_reader import CoverageReader
from p2pwatch.ports.driven.source_reader import SourceReader

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# Sort allowlist (webui spec §3.1): a sort maps to a FIXED ORDER BY expression; no param value is
# ever interpolated into SQL. ``tier`` sorts by the file's strongest tier rank
# (``dec.best_tier_rank``, MAX of the TIER_RANK CASE). Direction maps through a fixed set too.
SORT_COLUMNS: dict[CatalogEntrySort, str] = {
    CatalogEntrySort.NAME: "obs.filename",
    CatalogEntrySort.SIZE: "f.size_bytes",
    CatalogEntrySort.SOURCES: "obs.source_count",
    CatalogEntrySort.LAST_SEEN: "obs.observed_at",
    CatalogEntrySort.TIER: "dec.best_tier_rank",
}
SORT_DIRECTIONS: dict[SortDirection, str] = {SortDirection.ASC: "ASC", SortDirection.DESC: "DESC"}


def _tier_rank_case(column: str) -> str:
    """Generate a SQL CASE mapping a tier column to its ``TIER_RANK`` integer, from the trusted
    constant. ``TIER_RANK`` keys are the closed ``TIERS`` enum and its values are ints, so
    interpolating them is safe (no user input); this keeps ONE source of truth for tier order
    (the file's strongest tier = ``MAX`` of this expression)."""
    whens = " ".join(f"WHEN '{tier}' THEN {rank}" for tier, rank in TIER_RANK.items())
    return f"CASE {column} {whens} END"


_TIER_RANK_CASE = _tier_rank_case("ld.tier")

# Latest decision per (file_id, target_id) via ROW_NUMBER window: a whole-episode file holds
# one CURRENT decision per target it satisfies, so it must contribute to each of them, not
# just the single most-recent row across all its targets. The legacy target_id='' sentinel
# (pre-per-target retraction model) is excluded, and a per-target "retracted" latest decision
# (retracted == unmatched for that target) is dropped too.
_SQL_COVERAGE = """\
SELECT
    ld.file_id,
    ld.target_id,
    ld.tier
FROM (
    SELECT
        md.file_id,
        md.target_id,
        md.tier,
        ROW_NUMBER() OVER (
            PARTITION BY md.file_id, md.target_id
            ORDER BY md.decided_at DESC, md.id DESC
        ) AS rn
    FROM match_decisions AS md
) AS ld
WHERE ld.rn = 1
AND ld.target_id != ''
AND ld.tier != 'retracted'
ORDER BY ld.target_id, ld.file_id
"""

# The "latest per group" CTEs shared by the explorer list + counter, each folding an
# append-only table to its current rows (latest wins, tie-break on id).
#
# ``latest_observation`` (from ``observation_read``) seeks each file's newest observation by key
# instead of numbering the whole table with a window (11.6M rows on the node). It holds one row
# per catalogued file, all NULL for a file never seen; every consumer LEFT JOINs it onto ``files``,
# the counters only for a name filter, since the default page needs no name.
#
# ``latest_dec`` keeps the latest decision per (file_id, target_id), dropping the legacy
# ``target_id == ''`` sentinel and any target whose latest row is a ``retracted`` marker;
# ``dec_agg`` folds those to ONE row per file, target_ids/rule_names/tiers ``char(31)``-joined
# and all ordered by target_id so the lists stay index-aligned (spec §9, rendering A).
_SQL_CTES = f"""\
WITH latest_dec AS (
    SELECT file_id, target_id, rule_name, tier
    FROM (
        SELECT
            md.file_id,
            md.target_id,
            md.rule_name,
            md.tier,
            ROW_NUMBER() OVER (
                PARTITION BY md.file_id, md.target_id
                ORDER BY md.decided_at DESC, md.id DESC
            ) AS rn
        FROM match_decisions AS md
    )
    WHERE rn = 1
    AND target_id != ''
    AND tier != 'retracted'
),
dec_agg AS (
    SELECT
        ld.file_id,
        group_concat(ld.target_id, char(31) ORDER BY ld.target_id) AS target_ids,
        group_concat(ld.rule_name, char(31) ORDER BY ld.target_id) AS rule_names,
        group_concat(ld.tier, char(31) ORDER BY ld.target_id) AS tiers,
        MAX({_TIER_RANK_CASE}) AS best_tier_rank
    FROM latest_dec AS ld
    GROUP BY ld.file_id
),
{LATEST_OBSERVATION_CTE}
"""

# The shared source, files ⨝ latest observation ⨝ current decisions (aggregated), all pre-folded
# by the CTEs above, so it is a plain star-join driven by ``files``.
_JOIN_LATEST_OBSERVATION = "LEFT JOIN latest_observation AS obs ON obs.file_id = f.file_id\n"
_JOIN_DECISIONS = "LEFT JOIN dec_agg AS dec ON dec.file_id = f.file_id\n"

# Explorer: files + latest joins, driven by files; read_catalog_entries() adds the filters.
# The latest observation's columns first, in the order ``observation_from_row`` maps them.
_SQL_LIST_FILES_BASE = (
    _SQL_CTES
    + """\
SELECT
    obs.network,
    obs.native_id,
    obs.filename,
    obs.size_bytes,
    obs.source_count,
    obs.keyword,
    obs.duration_seconds,
    obs.bitrate_kbps,
    obs.raw_meta,
    obs.observed_at,
    f.size_bytes AS file_size_bytes,
    dec.target_ids,
    dec.rule_names,
    dec.tiers
FROM files AS f
"""
    + _JOIN_LATEST_OBSERVATION
    + _JOIN_DECISIONS
)

# Counter for the /files summary: file-based totals over the same source + filters (the
# matched-only clause is deliberately absent). ``matched`` = files with at least one current
# decision (``dec.target_ids`` is non-NULL). COUNT(DISTINCT …) keeps both counts file-based
# and yields 0 (not NULL) on an empty catalogue. read_matched_and_total_file_counts() appends
# the joins.
_SQL_COUNT_FILES_BASE = (
    _SQL_CTES
    + """\
SELECT
    COUNT(DISTINCT f.file_id) AS total,
    COUNT(DISTINCT CASE WHEN dec.target_ids IS NOT NULL THEN f.file_id END) AS matched
FROM files AS f
"""
)

# Tier facet counts (webui spec §3.3): one row per tier, ``COUNT(DISTINCT file_id)`` files that
# have at least one CURRENT decision of that tier. Grouped over ``latest_dec`` (per-decision), so
# a multi-tier file counts once under each of its tiers. The tier filter itself is NEVER applied
# here (a facet shows the count you would get by choosing each option).
_SQL_TIER_COUNTS_BASE = (
    _SQL_CTES
    + """\
SELECT ld.tier AS tier, COUNT(DISTINCT ld.file_id) AS n
FROM latest_dec AS ld
JOIN files AS f ON f.file_id = ld.file_id
"""
)

# All current decisions of a file: latest per (file_id, target_id), excluding the legacy
# ``target_id == ''`` sentinel and any target whose latest row is a ``retracted`` marker.
_SQL_FILE_DECISIONS = """\
SELECT target_id, rule_name, tier, decided_at, node_id
FROM (
    SELECT
        md.target_id,
        md.rule_name,
        md.tier,
        md.decided_at,
        md.node_id,
        ROW_NUMBER() OVER (
            PARTITION BY md.target_id
            ORDER BY md.decided_at DESC, md.id DESC
        ) AS rn
    FROM match_decisions AS md
    WHERE md.file_id = ?
)
WHERE rn = 1
AND target_id != ''
AND tier != 'retracted'
ORDER BY target_id
"""

# Basic lookup on files (for read_file_history).
_SQL_FILE = """\
SELECT network, native_id, size_bytes
FROM files
WHERE file_id = ?
"""

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
        MAX({_SQL_VARIANT_LAST_SEEN}) AS last_seen_at,
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
    seen.last_seen_at,
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
    MAX({_SQL_VARIANT_LAST_SEEN}) AS last_seen_at,
    COUNT(DISTINCT v.file_id) AS file_count
FROM source_variants AS v
JOIN sources AS s ON s.source_id = v.source_id
"""
_SQL_PAIRS_END = """\
GROUP BY v.source_id, v.name
ORDER BY last_seen_at DESC, v.source_id, v.name
LIMIT :limit OFFSET :offset
"""

# The WHERE of each read: a hash page lists names and a name page hashes, nothing further.
_WHERE_FILE = "WHERE v.file_id = :key\n"
_WHERE_SOURCE = "WHERE v.source_id = :key\n"
_WHERE_SOURCE_NAMED = "WHERE v.source_id = :key AND v.name IS NOT NULL\n"
_WHERE_NAME = "WHERE v.name = :key\n"
_WHERE_NAME_HASHLESS = "WHERE v.name = :key AND v.source_id IS NULL\n"


def _filter_clauses(
    target_id: str | None,
    tier: str | None,
    search_text: str | None,
) -> tuple[list[str], list[str]]:
    """Shared WHERE clauses + params for the explorer list and its counter.

    ``target_id``/``tier`` match a file if ANY of its current decisions matches (EXISTS over the
    ``latest_dec`` CTE), so a whole-episode file appears under each of its targets. The
    ``target_id`` clause additionally excludes ``catalog``-tier rows (they are pinned to ``001A``),
    consistent with ``coverage_of``. The matched-only clause and LIMIT/OFFSET are list-specific
    and are NOT built here.
    """
    clauses: list[str] = []
    params: list[str] = []
    if target_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM latest_dec AS fdt"
            " WHERE fdt.file_id = f.file_id AND fdt.target_id = ? AND fdt.tier != 'catalog')"
        )
        params.append(target_id)
    if tier is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM latest_dec AS fdt"
            " WHERE fdt.file_id = f.file_id AND fdt.tier = ?)"
        )
        params.append(tier)
    if search_text is not None:
        clauses.append("obs.filename LIKE ?")
        params.append(f"%{search_text}%")
    return clauses, params


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
            last_seen_at=_EPOCH + row["last_seen_at"] * _MICROSECOND,
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


def _latest_observation_join(search_text: str | None) -> str:
    """The counters' join to the latest observation, which only the name filter reads."""
    return "" if search_text is None else _JOIN_LATEST_OBSERVATION


def _split_concat(concat: str | None) -> list[str]:
    """Split a ``char(31)``-joined aggregate (``group_concat``) into parts. ``None`` (a file
    with no current decision → the LEFT JOIN yields NULL) → an empty list."""
    return concat.split("\x1f") if concat is not None else []


class SqliteCoverageReader(CoverageReader):
    """Reads through the calling thread's read-only connection."""

    def __init__(self, reader_provider: ReaderProvider) -> None:
        self._reader_provider = reader_provider

    def read_target_coverage(self) -> dict[str, tuple[str, ...]]:
        tiers_by_target: dict[str, list[str]] = {}
        for row in self._reader_provider.connection().execute(_SQL_COVERAGE):
            tiers_by_target.setdefault(row["target_id"], []).append(row["tier"])
        return {target_id: tuple(tiers) for target_id, tiers in tiers_by_target.items()}


class SqliteSourceReader(SourceReader):
    """Reads through the calling thread's read-only connection."""

    def __init__(self, reader_provider: ReaderProvider) -> None:
        self._reader_provider = reader_provider

    def read_known_sources(
        self, *, search_text: str | None, limit: int, offset: int
    ) -> tuple[KnownSource, ...]:
        search, params = _sources_search(search_text)
        sql = (
            _SQL_LIST_SOURCES_SELECT
            + _SQL_SOURCES_FROM
            + search
            + "ORDER BY seen.last_seen_at DESC, s.source_id\nLIMIT ? OFFSET ?\n"
        )
        rows = self._reader_provider.connection().execute(sql, [*params, limit, offset])
        return tuple(
            KnownSource(
                source=SourceKey(Network(row["network"]), row["native_id"]),
                source_name=row["name"],
                last_seen_at=_EPOCH + row["last_seen_at"] * _MICROSECOND,
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


# ---------------------------------------------------------------------------
# SqliteCatalogFileReader
# ---------------------------------------------------------------------------


class SqliteCatalogFileReader(CatalogFileReader):
    """Reads through the calling thread's read-only connection."""

    def __init__(self, reader_provider: ReaderProvider) -> None:
        self._reader_provider = reader_provider

    def read_matched_and_total_file_counts(
        self,
        *,
        target_id: str | None,
        tier: str | None,
        search_text: str | None,
    ) -> tuple[int, int]:
        """Not narrowed by the files page's ``matched_only``."""
        clauses, params = _filter_clauses(target_id, tier, search_text)
        sql = _SQL_COUNT_FILES_BASE + _latest_observation_join(search_text) + _JOIN_DECISIONS
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + "\n"
        row = self._reader_provider.connection().execute(sql, params).fetchone()
        matched: int = row["matched"]
        total: int = row["total"]
        return (matched, total)

    def read_file_count_by_tier(
        self,
        *,
        target_id: str | None,
        search_text: str | None,
    ) -> Mapping[str, int]:
        """Never a tier filter: each facet shows the count its choice would give; a multi-tier
        file counts under each of its tiers."""
        clauses, params = _filter_clauses(target_id, None, search_text)
        sql = _SQL_TIER_COUNTS_BASE + _latest_observation_join(search_text)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + "\n"
        sql += "GROUP BY ld.tier\n"
        rows = self._reader_provider.connection().execute(sql, params).fetchall()
        return {row["tier"]: row["n"] for row in rows}

    # ------------------------------------------------------------------
    # Filtered paginated explorer
    # ------------------------------------------------------------------

    def read_catalog_entries(
        self,
        *,
        target_id: str | None,
        tier: str | None,
        search_text: str | None,
        matched_only: bool,
        sort: CatalogEntrySort,
        direction: SortDirection,
        limit: int,
        offset: int,
    ) -> tuple[CatalogEntry, ...]:
        """``tier`` sorts on the strongest tier; a file never seen sorts first in ASC (NULLs
        first), and the ``file_id`` tiebreak keeps paging stable."""
        clauses, str_params = _filter_clauses(target_id, tier, search_text)
        if matched_only:
            # A file is matched iff it has at least one current (non-retracted) decision;
            # ``dec.target_ids`` is NULL for a file with none.
            clauses.append("dec.target_ids IS NOT NULL")
        params: list[str | int] = [*str_params]

        sql = _SQL_LIST_FILES_BASE
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + "\n"
        # ORDER BY from the allowlist (spec §3.1): both operands come from fixed maps, never
        # from a raw param, so the f-string is injection-safe.
        sql += f"ORDER BY {SORT_COLUMNS[sort]} {SORT_DIRECTIONS[direction]}, f.file_id\n"
        sql += "LIMIT ? OFFSET ?\n"
        params.append(limit)
        params.append(offset)

        rows = self._reader_provider.connection().execute(sql, params).fetchall()
        return tuple(
            CatalogEntry(
                file=FileKey(Network(row["network"]), row["native_id"]),
                size_bytes=row["file_size_bytes"],
                # A file with no observation LEFT JOINs to NULLs.
                latest_observation=None if row["filename"] is None else observation_from_row(row),
                decisions=tuple(
                    DecisionRecord(target_id=t, rule_name=r, tier=ti)
                    for t, r, ti in zip(
                        _split_concat(row["target_ids"]),
                        _split_concat(row["rule_names"]),
                        _split_concat(row["tiers"]),
                        strict=True,
                    )
                ),
            )
            for row in rows
        )

    def read_file_history(
        self, file_id: bytes, *, since: datetime, until: datetime
    ) -> FileHistory | None:
        connection = self._reader_provider.connection()
        file_row = connection.execute(_SQL_FILE, (file_id,)).fetchone()
        if file_row is None:
            return None

        file = FileKey(Network(file_row["network"]), file_row["native_id"])
        dec_rows = connection.execute(_SQL_FILE_DECISIONS, (file_id,)).fetchall()

        decisions = tuple(
            DatedDecision(
                DecisionRecord(
                    target_id=row["target_id"], rule_name=row["rule_name"], tier=row["tier"]
                ),
                decided_at=datetime.fromisoformat(row["decided_at"]),
                node_id=row["node_id"],
            )
            for row in dec_rows
        )

        return FileHistory(
            file=file,
            size_bytes=file_row["size_bytes"],
            observations=observations_between(connection, file, _micros(since), _micros(until)),
            latest_observation=latest_observation(connection, file),
            decisions=decisions,
            known_filenames=known_filenames(connection, file),
        )
