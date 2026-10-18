"""Read-only reads of the catalog (webui spec W-D6 / §6).

``CatalogReader`` exposes these reads:

- ``target_coverage()``: per ``target_id``, the list of ``(file_id, tier)`` from each
  file's LATEST match decision **per target** (ROW_NUMBER window PARTITION BY
  ``(file_id, target_id)``), so a whole-episode file contributes to every target it
  matches. The legacy ``target_id=''`` sentinel and per-target ``retracted`` rows are
  excluded.
- ``list_files()``: filtered paginated explorer (files ⨝ latest observation ⨝
  latest decision, optional filters + LIMIT/OFFSET).
- ``count_files()``: ``(matched, total)`` counts over the same filtered source, for the
  /files summary line.
- ``file_detail()``: the timeline of sightings in a window, the latest one, known names + current
  decisions for a given ``file_id``; ``None`` if the file is unknown.
- ``source_periods()``: a file's source history in a window, one period per row, newest first.
- ``list_sources()`` / ``count_sources()``: the sources with a user hash, last seen first, and
  how many match the search.
- ``source_detail()`` / ``name_detail()``: the page of a source and the page of a name; ``None``
  if never recorded.

All SQL lives in module constants, parameterized (no value interpolation).
"""

import sqlite3

from catalog_matching.domain.config import TIER_RANK
from p2pwatch.adapters.driven.persistence_sqlite.sightings import (
    LATEST_SIGHTING_CTE,
    best_filename_and_size,
    known_filenames,
    latest_sighting,
    sightings,
)
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.source import SourceKey, SourceRole
from p2pwatch.webui.domain.views import (
    DecisionView,
    FileDecision,
    FileDetail,
    FileRow,
    NameDetail,
    PeriodWindow,
    SourceDetail,
    SourceFilePeriod,
    SourcePeriodView,
    SourceRow,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PAGE_SIZE = 50
_PAGE_SIZE = PAGE_SIZE  # historical alias (internal); the public value is used by the handler

# Sort allowlist (webui spec §3.1): a query-param key maps to a FIXED ORDER BY expression; no
# param value is ever interpolated into SQL. ``tier`` sorts by the file's strongest tier rank
# (``dec.best_tier_rank``, MAX of the TIER_RANK CASE). Direction maps through a fixed set too.
SORT_COLUMNS: dict[str, str] = {
    "name": "obs.filename",
    "size": "f.size_bytes",
    "sources": "obs.source_count",
    "last_seen": "obs.last_seen",
    "tier": "dec.best_tier_rank",
}
SORT_DIRECTIONS: dict[str, str] = {"asc": "ASC", "desc": "DESC"}
DEFAULT_SORT = "last_seen"
DEFAULT_DIR = "desc"


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
# ``latest_sighting`` (from ``sightings``) seeks each file's newest observation by key instead of
# numbering the whole table with a window (11.6M rows on the node). It holds one row per
# catalogued file, all NULL for a file never seen; every consumer LEFT JOINs it onto ``files``,
# the counters only for a name filter, since the default page needs no name.
#
# ``latest_dec`` keeps the latest decision per (file_id, target_id), dropping the legacy
# ``target_id == ''`` sentinel and any target whose latest row is a ``retracted`` marker;
# ``dec_agg`` folds those to ONE row per file, target_ids/tiers ``char(31)``-joined and both
# ordered by target_id so the two lists stay index-aligned (spec §9, rendering A).
_SQL_CTES = f"""\
WITH latest_dec AS (
    SELECT file_id, target_id, tier
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
    )
    WHERE rn = 1
    AND target_id != ''
    AND tier != 'retracted'
),
dec_agg AS (
    SELECT
        ld.file_id,
        group_concat(ld.target_id, char(31) ORDER BY ld.target_id) AS target_ids,
        group_concat(ld.tier, char(31) ORDER BY ld.target_id) AS tiers,
        MAX({_TIER_RANK_CASE}) AS best_tier_rank
    FROM latest_dec AS ld
    GROUP BY ld.file_id
),
{LATEST_SIGHTING_CTE}
"""

# The shared source, files ⨝ latest observation ⨝ current decisions (aggregated), all pre-folded
# by the CTEs above, so it is a plain star-join driven by ``files``.
_JOIN_LATEST_SIGHTING = "LEFT JOIN latest_sighting AS obs ON obs.file_id = f.file_id\n"
_JOIN_DECISIONS = "LEFT JOIN dec_agg AS dec ON dec.file_id = f.file_id\n"

# Explorer: files + latest joins, driven by files. Optional filters added in list_files().
_SQL_LIST_FILES_BASE = (
    _SQL_CTES
    + """\
SELECT
    f.network,
    f.native_id,
    f.size_bytes,
    obs.filename AS filename,
    obs.source_count AS source_count,
    obs.last_seen AS last_seen,
    dec.target_ids,
    dec.tiers
FROM files AS f
"""
    + _JOIN_LATEST_SIGHTING
    + _JOIN_DECISIONS
)

# Counter for the /files summary: file-based totals over the same source + filters (the
# matched-only clause is deliberately absent). ``matched`` = files with at least one current
# decision (``dec.target_ids`` is non-NULL). COUNT(DISTINCT …) keeps both counts file-based
# and yields 0 (not NULL) on an empty catalogue. count_files() appends the joins.
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

# Basic lookup on files (for file_detail).
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
    target: str | None,
    tier: str | None,
    query: str | None,
) -> tuple[list[str], list[str]]:
    """Shared WHERE clauses + params for the explorer list and its counter.

    ``target``/``tier`` match a file if ANY of its current decisions matches (EXISTS over the
    ``latest_dec`` CTE), so a whole-episode file appears under each of its targets. The
    ``target`` clause additionally excludes ``catalog``-tier rows (they are pinned to ``001A``),
    consistent with ``coverage_of``. The matched-only clause and LIMIT/OFFSET are list-specific
    and are NOT built here.
    """
    clauses: list[str] = []
    params: list[str] = []
    if target is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM latest_dec AS fdt"
            " WHERE fdt.file_id = f.file_id AND fdt.target_id = ? AND fdt.tier != 'catalog')"
        )
        params.append(target)
    if tier is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM latest_dec AS fdt"
            " WHERE fdt.file_id = f.file_id AND fdt.tier = ?)"
        )
        params.append(tier)
    if query is not None:
        clauses.append("obs.filename LIKE ?")
        params.append(f"%{query}%")
    return clauses, params


def _sources_search(query: str | None) -> tuple[str, list[str]]:
    """The sources list's search clause and its parameters; none without a query."""
    if query is None:
        return "", []
    return _SQL_SOURCES_SEARCH, [f"{query}%", f"%{query}%"]


def _period_view(row: sqlite3.Row) -> SourcePeriodView:
    """A row of ``_SQL_PERIODS`` as a period; only a sending one received its growth (D6)."""
    network, connectable = row["network"], row["connectable"]
    role = SourceRole(row["role"])
    return SourcePeriodView(
        source=None if network is None else SourceKey(Network(network), row["native_id"]),
        name=row["name"],
        role=role,
        contact_point=row["contact_point"],
        connectable=None if connectable is None else bool(connectable),
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        received_bytes=row["growth"] if role is SourceRole.SENDING else 0,
        node_id=row["node_id"],
    )


def _latest_sighting_join(query: str | None) -> str:
    """The counters' join to the latest sighting, which only the name filter reads."""
    return "" if query is None else _JOIN_LATEST_SIGHTING


def _split_concat(concat: str | None) -> list[str]:
    """Split a ``char(31)``-joined aggregate (``group_concat``) into parts. ``None`` (a file
    with no current decision → the LEFT JOIN yields NULL) → an empty list."""
    return concat.split("\x1f") if concat is not None else []


# ---------------------------------------------------------------------------
# CatalogReader
# ---------------------------------------------------------------------------


class CatalogReader:
    """Read-only access to the catalog via a SQLite connection (see ``reader.open_reader``)."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def target_coverage(self) -> dict[str, list[tuple[bytes, str]]]:
        """Return, for each ``target_id``, the list of ``(file_id, tier)``
        from each file's LATEST match decision **per target** (a whole-episode
        file appears under every target it currently matches).
        """
        rows = self._conn.execute(_SQL_COVERAGE).fetchall()
        result: dict[str, list[tuple[bytes, str]]] = {}
        for row in rows:
            target_id: str = row["target_id"]
            entry = (row["file_id"], row["tier"])
            if target_id not in result:
                result[target_id] = []
            result[target_id].append(entry)
        return result

    # ------------------------------------------------------------------
    # Filtered paginated explorer
    # ------------------------------------------------------------------

    def list_files(
        self,
        *,
        target: str | None,
        tier: str | None,
        query: str | None,
        page: int,
        matched_only: bool = False,
        sort: str = DEFAULT_SORT,
        direction: str = DEFAULT_DIR,
    ) -> list[FileRow]:
        """Return a page of ``FileRow`` (size ``_PAGE_SIZE``) with optional filters.

        Filters:
        - ``target`` : keep a file if ANY of its current decisions matches this target_id.
        - ``tier``   : keep a file if ANY of its current decisions has this tier.
        - ``query``  : substring (LIKE ``%query%``) of the latest name.
        - ``matched_only``: when true, keep only files with at least one current decision
          (retractions and the legacy ``target_id == ''`` sentinel never produce one).
          Default false = whole catalogue.
        - ``page``   : page number (1-based).

        Sort:
        - ``sort``     : one of the ``SORT_COLUMNS`` allowlist keys
          (``name``/``size``/``sources``/``last_seen``/``tier``); an unknown key falls back to
          ``DEFAULT_SORT`` (``last_seen``). ``tier`` sorts by the file's strongest tier rank.
        - ``direction``: ``asc`` or ``desc``; an unknown value falls back to ``DEFAULT_DIR``
          (``desc``). SQLite sorts NULLs first in ASC, so a NULL ``filename``/``observed_at``
          (a file with no observation) clusters predictably. The ``file_id`` tiebreak keeps
          paging stable.
        """
        clauses, str_params = _filter_clauses(target, tier, query)
        if matched_only:
            # A file is matched iff it has at least one current (non-retracted) decision;
            # ``dec.target_ids`` is NULL for a file with none.
            clauses.append("dec.target_ids IS NOT NULL")
        params: list[str | int] = [*str_params]

        sql = _SQL_LIST_FILES_BASE
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + "\n"
        # ORDER BY from the allowlist (spec §3.1): unknown sort/direction fall back to the
        # default; the file_id tiebreak keeps paging stable. Both operands come from fixed
        # maps, never from the raw param, so the f-string is injection-safe.
        column_expr = SORT_COLUMNS.get(sort, SORT_COLUMNS[DEFAULT_SORT])
        dir_sql = SORT_DIRECTIONS.get(direction, SORT_DIRECTIONS[DEFAULT_DIR])
        sql += f"ORDER BY {column_expr} {dir_sql}, f.file_id\n"
        sql += "LIMIT ? OFFSET ?\n"
        params.append(_PAGE_SIZE)
        params.append((page - 1) * _PAGE_SIZE)

        rows = self._conn.execute(sql, params).fetchall()
        result: list[FileRow] = []
        for row in rows:
            target_ids = _split_concat(row["target_ids"])
            tiers = _split_concat(row["tiers"])
            decisions = tuple(
                FileDecision(target_id=t, tier=ti) for t, ti in zip(target_ids, tiers, strict=True)
            )
            result.append(
                FileRow(
                    file=FileKey(Network(row["network"]), row["native_id"]),
                    size_bytes=row["size_bytes"],
                    # A file with no observation LEFT JOINs to NULLs; an unknown count stays None.
                    filename=row["filename"] or "",
                    source_count=row["source_count"],
                    last_seen=row["last_seen"] or "",
                    decisions=decisions,
                )
            )
        return result

    def count_files(
        self,
        *,
        target: str | None,
        tier: str | None,
        query: str | None,
    ) -> tuple[int, int]:
        """Return ``(matched, total)`` file counts in the current filter scope.

        ``total`` = files matching the ``target/tier/query`` filters (the
        matched-only clause is deliberately NOT applied); ``matched`` = of those, how many
        have a match decision. Feeds the /files summary line.
        """
        clauses, params = _filter_clauses(target, tier, query)
        sql = _SQL_COUNT_FILES_BASE + _latest_sighting_join(query) + _JOIN_DECISIONS
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + "\n"
        row = self._conn.execute(sql, params).fetchone()
        matched: int = row["matched"]
        total: int = row["total"]
        return (matched, total)

    def tier_counts(
        self,
        *,
        target: str | None,
        query: str | None,
    ) -> dict[str, int]:
        """Return ``{tier: file_count}`` for the tier facet, applying the ``target``/``query``
        filters but NEVER a tier filter (facet-lite: each option shows the count you
        would get by choosing it). A file counts under every tier it currently holds a decision
        in (a multi-tier file appears in two facets). ``{}`` on an empty/undecided catalogue.
        """
        clauses, params = _filter_clauses(target, None, query)
        sql = _SQL_TIER_COUNTS_BASE + _latest_sighting_join(query)
        if clauses:
            sql += "WHERE " + " AND ".join(clauses) + "\n"
        sql += "GROUP BY ld.tier\n"
        rows = self._conn.execute(sql, params).fetchall()
        return {row["tier"]: row["n"] for row in rows}

    # ------------------------------------------------------------------
    # Detail
    # ------------------------------------------------------------------

    def file_detail(self, file_id: bytes, window: PeriodWindow) -> FileDetail | None:
        """Return the full detail of a file, its timeline in ``window``, or ``None`` if unknown."""
        file_row = self._conn.execute(_SQL_FILE, (file_id,)).fetchone()
        if file_row is None:
            return None

        file = FileKey(Network(file_row["network"]), file_row["native_id"])
        dec_rows = self._conn.execute(_SQL_FILE_DECISIONS, (file_id,)).fetchall()

        decisions = tuple(
            DecisionView(
                target_id=row["target_id"],
                rule_name=row["rule_name"],
                tier=row["tier"],
                decided_at=row["decided_at"],
                node_id=row["node_id"],
            )
            for row in dec_rows
        )

        return FileDetail(
            file=file,
            size_bytes=file_row["size_bytes"],
            sightings=sightings(self._conn, file, window.since, window.until),
            latest=latest_sighting(self._conn, file),
            decisions=decisions,
            known_filenames=known_filenames(self._conn, file),
        )

    def source_periods(self, file_id: bytes, window: PeriodWindow) -> tuple[SourcePeriodView, ...]:
        """The file's source periods in ``window``, newest first; empty for a file never read."""
        return tuple(map(_period_view, self._periods(_WHERE_FILE, file_id, window)))

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def list_sources(self, *, query: str | None, page: int) -> tuple[SourceRow, ...]:
        """A page of sources, last seen first; ``query`` as ``_SQL_SOURCES_SEARCH`` reads it."""
        search, params = _sources_search(query)
        sql = (
            _SQL_LIST_SOURCES_SELECT
            + _SQL_SOURCES_FROM
            + search
            + "ORDER BY seen.last_seen_at DESC, s.source_id\nLIMIT ? OFFSET ?\n"
        )
        rows = self._conn.execute(sql, [*params, _PAGE_SIZE, (page - 1) * _PAGE_SIZE])
        return tuple(
            SourceRow(
                source=SourceKey(Network(row["network"]), row["native_id"]),
                name=row["name"],
                last_seen_at=row["last_seen_at"],
                file_count=row["file_count"],
            )
            for row in rows
        )

    def count_sources(self, *, query: str | None) -> int:
        """How many sources ``list_sources`` pages through for this ``query``."""
        search, params = _sources_search(query)
        row = self._conn.execute("SELECT COUNT(*) AS n\n" + _SQL_SOURCES_FROM + search, params)
        count: int = row.fetchone()["n"]
        return count

    def source_detail(
        self, source_id: bytes, *, page: int, window: PeriodWindow
    ) -> SourceDetail | None:
        """A page of the source's names, and its periods in ``window``; ``None`` for an unknown
        source."""
        row = self._conn.execute(_SQL_SOURCE, (source_id,)).fetchone()
        if row is None:
            return None
        source = SourceKey(Network(row["network"]), row["native_id"])
        return SourceDetail(
            source=source,
            names=self._pairs(_WHERE_SOURCE_NAMED, source_id, page),
            periods=self._file_periods(_WHERE_SOURCE, source_id, window),
        )

    def name_detail(self, name: str, *, page: int, window: PeriodWindow) -> NameDetail | None:
        """A page of the hashes that carried the name, and its hash-less periods in ``window``;
        ``None`` for a name never recorded."""
        if self._conn.execute(_SQL_NAME_EXISTS, (name,)).fetchone() is None:
            return None
        return NameDetail(
            name=name,
            sources=self._pairs(_WHERE_NAME, name, page),
            periods=self._file_periods(_WHERE_NAME_HASHLESS, name, window),
        )

    def _pairs(self, where: str, key: bytes | str, page: int) -> tuple[SourceRow, ...]:
        params = {"key": key, "limit": _PAGE_SIZE, "offset": (page - 1) * _PAGE_SIZE}
        rows = self._conn.execute(_SQL_PAIRS + where + _SQL_PAIRS_END, params)
        return tuple(
            SourceRow(
                source=SourceKey(Network(row["network"]), row["native_id"]),
                name=row["name"],
                last_seen_at=row["last_seen_at"],
                file_count=row["file_count"],
            )
            for row in rows
        )

    def _periods(self, where: str, key: bytes | str, window: PeriodWindow) -> list[sqlite3.Row]:
        params = {
            "key": key,
            "since": window.since,
            "until": window.until,
            "gap": window.gap,
        }
        return self._conn.execute(_SQL_PERIODS + where + _SQL_PERIODS_END, params).fetchall()

    def _file_periods(
        self, where: str, key: bytes | str, window: PeriodWindow
    ) -> tuple[SourceFilePeriod, ...]:
        rows = self._periods(where, key, window)
        files = [FileKey(Network(row["file_network"]), row["file_native_id"]) for row in rows]
        names = {file: self._file_name(file) for file in set(files)}
        return tuple(
            SourceFilePeriod(file=file, file_name=names[file], period=_period_view(row))
            for file, row in zip(files, rows, strict=True)
        )

    def _file_name(self, file: FileKey) -> str | None:
        named = best_filename_and_size(self._conn, file)
        return None if named is None else named[0]
