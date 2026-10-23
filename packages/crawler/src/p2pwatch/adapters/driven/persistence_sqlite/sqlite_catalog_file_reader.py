"""Read-only reads of the catalog (webui spec W-D6 / §6).

``SqliteCatalogFileReader`` reads the files page: its entries (files ⨝ latest observation ⨝
current decisions, optional filters + LIMIT/OFFSET), their ``(matched, total)`` counts and their
tier facet; and a file's history: its observations in an interval, its latest one, its known names
and its current decisions, ``None`` if the file is unknown.

All SQL lives in module constants, parameterized (no value interpolation).
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.adapters.driven.persistence_sqlite.observation_read import (
    LATEST_OBSERVATION_CTE,
    known_filenames,
    latest_observation,
    observation_from_row,
    observations_between,
)
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import DatedDecision, FileHistory
from p2pwatch.domain.file_key import FileKey, Network

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)

# Sort allowlist (webui spec §3.1): a sort maps to a FIXED ORDER BY expression; no param value is
# ever interpolated into SQL. ``tier`` sorts by the file's strongest tier rank
# (``dec.best_tier_rank``, MAX of the tier rank CASE). Direction maps through a fixed set too.
SORT_COLUMNS: dict[CatalogEntrySort, str] = {
    CatalogEntrySort.NAME: "obs.filename",
    CatalogEntrySort.SIZE: "f.size_bytes",
    CatalogEntrySort.SOURCES: "obs.source_count",
    CatalogEntrySort.LATEST_SEEN: "obs.observed_at",
    CatalogEntrySort.TIER: "dec.best_tier_rank",
}
SORT_DIRECTIONS: dict[SortDirection, str] = {SortDirection.ASC: "ASC", SortDirection.DESC: "DESC"}


def _tier_rank_case(column: str) -> str:
    """Generate a SQL CASE mapping a tier column to its ``DecisionTier.rank``, from the closed
    enum (no user input, safe to interpolate): the file's strongest tier is its ``MAX``."""
    whens = " ".join(f"WHEN '{tier}' THEN {tier.rank}" for tier in DecisionTier)
    return f"CASE {column} {whens} END"


_TIER_RANK_CASE = _tier_rank_case("ld.tier")

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
    obs.raw_metadata,
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


def _micros(moment: datetime) -> int:
    return (moment - _EPOCH) // _MICROSECOND


def _latest_observation_join(search_text: str | None) -> str:
    """The counters' join to the latest observation, which only the name filter reads."""
    return "" if search_text is None else _JOIN_LATEST_OBSERVATION


def _split_concat(concat: str | None) -> list[str]:
    """Split a ``char(31)``-joined aggregate (``group_concat``) into parts. ``None`` (a file
    with no current decision → the LEFT JOIN yields NULL) → an empty list."""
    return concat.split("\x1f") if concat is not None else []


# ---------------------------------------------------------------------------
# SqliteCatalogFileReader
# ---------------------------------------------------------------------------


class SqliteCatalogFileReader(CatalogFileReader):
    """Reads through the calling thread's read-only connection."""

    def __init__(self, thread_read_connections: ThreadReadConnections) -> None:
        self._thread_read_connections = thread_read_connections

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
        row = self._thread_read_connections.connection().execute(sql, params).fetchone()
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
        rows = self._thread_read_connections.connection().execute(sql, params).fetchall()
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

        rows = self._thread_read_connections.connection().execute(sql, params).fetchall()
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
        connection = self._thread_read_connections.connection()
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
