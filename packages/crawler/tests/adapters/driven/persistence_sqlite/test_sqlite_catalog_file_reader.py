"""TDD tests for the catalog's file reader: filtered explorer, file history (spec W-D6 / §6)."""

import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_catalog_file_reader import (
    _JOIN_DECISIONS,
    _JOIN_LATEST_OBSERVATION,
    _SQL_COUNT_FILES_BASE,
    _SQL_CTES,
    _SQL_LIST_FILES_BASE,
    _SQL_TIER_COUNTS_BASE,
    SORT_COLUMNS,
    SqliteCatalogFileReader,
    _tier_rank_case,
)
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_decision_store import SqliteDecisionStore
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import FileHistory
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.file_target_decision import DatedDecision
from p2pwatch.domain.identifiers import FileId, Keyword, NodeId
from p2pwatch.domain.observation import FileObservation, ReportedFile
from tests.support.adapters.driven.persistence_sqlite.catalog_seeds import (
    seed,
    seed_retracted,
    seed_whole_episode,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import open_reader
from tests.support.catalog_rows import (
    SEEN_AT,
    file_id,
    insert_decision,
    insert_file,
    insert_observation,
)

# Selects the CTE under test on its own: SQLite drops the CTEs a query does not reference, so
# the resulting plan is exactly how ``latest_observation`` is resolved.
LATEST_OBSERVATION_PROBE = (
    "SELECT file_id, filename, source_count, observed_at_micros FROM latest_observation"
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_YEAR_3000 = datetime(3000, 1, 1, tzinfo=UTC)  # after every instant a test writes
_LIMIT = 50


def _entries(
    catalog_db: Path,
    *,
    target_id: TargetId | None = None,
    tier: DecisionTier | None = None,
    search_text: str | None = None,
    matched_only: bool = False,
    sort: CatalogEntrySort = CatalogEntrySort.LATEST_SEEN,
    direction: SortDirection = SortDirection.DESC,
    offset: int = 0,
) -> tuple[CatalogEntry, ...]:
    with ThreadReadConnections(catalog_db, open_reader) as thread_read_connections:
        return SqliteCatalogFileReader(thread_read_connections).read_catalog_entries(
            target_id=target_id,
            tier=tier,
            search_text=search_text,
            matched_only=matched_only,
            sort=sort,
            direction=direction,
            limit=_LIMIT,
            offset=offset,
        )


def _counts(
    catalog_db: Path,
    *,
    target_id: TargetId | None = None,
    tier: DecisionTier | None = None,
    search_text: str | None = None,
) -> tuple[int, int]:
    with ThreadReadConnections(catalog_db, open_reader) as thread_read_connections:
        return SqliteCatalogFileReader(thread_read_connections).read_matched_and_total_file_counts(
            target_id=target_id, tier=tier, search_text=search_text
        )


def _read_file_count_by_tier(
    catalog_db: Path, *, search_text: str | None = None
) -> Mapping[DecisionTier, int]:
    with ThreadReadConnections(catalog_db, open_reader) as thread_read_connections:
        return SqliteCatalogFileReader(thread_read_connections).read_file_count_by_tier(
            target_id=None, search_text=search_text
        )


def _latest_filename(catalog_entry: CatalogEntry) -> str | None:
    observation = catalog_entry.latest_observation
    return None if observation is None else observation.reported_file.filename


# ---------------------------------------------------------------------------
# Tests: explorer, filters present / absent
# ---------------------------------------------------------------------------


def test_read_catalog_entries_no_filter_returns_all(catalog_db: Path) -> None:
    seed(catalog_db)
    rows = _entries(catalog_db)
    assert rows == (
        CatalogEntry(
            file=FileKey(network=Network.ED2K, native_id="a" * 32),
            size_bytes=100,
            latest_observation=FileObservation(
                reported_file=ReportedFile(
                    file=FileKey(network=Network.ED2K, native_id="a" * 32),
                    filename="keroro_062.avi",
                    size_bytes=100,
                    source_count=5,
                    keyword=Keyword("keroro"),
                ),
                observed_at=datetime(2026, 6, 22, 10, tzinfo=UTC),
                node_id=NodeId("n1"),
            ),
            decisions=(
                DecisionRecord(
                    target_id=TargetId("062A"),
                    rule_name="id_segment_exact",
                    tier=DecisionTier.DOWNLOAD,
                ),
            ),
        ),
    )


def test_read_catalog_entries_filter_by_target(catalog_db: Path) -> None:
    seed(catalog_db)
    hit = _entries(catalog_db, target_id=TargetId("062A"))
    miss = _entries(catalog_db, target_id=TargetId("001A"))
    assert len(hit) == 1
    assert miss == ()


def test_read_catalog_entries_filter_by_tier(catalog_db: Path) -> None:
    seed(catalog_db)
    hit = _entries(catalog_db, tier=DecisionTier.DOWNLOAD)
    miss = _entries(catalog_db, tier=DecisionTier.NOTIFY)
    assert len(hit) == 1
    assert miss == ()


def test_read_catalog_entries_filter_by_search_text(catalog_db: Path) -> None:
    seed(catalog_db)
    hit = _entries(catalog_db, search_text="keroro")
    miss = _entries(catalog_db, search_text="unknown")
    assert len(hit) == 1
    assert miss == ()


def test_read_catalog_entries_reads_none_past_the_offset(catalog_db: Path) -> None:
    seed(catalog_db)
    assert _entries(catalog_db, offset=1) == ()


# ---------------------------------------------------------------------------
# Tests: read_catalog_entries / read_matched_and_total_file_counts: one row per file, decisions
# aggregated (spec §9)
# ---------------------------------------------------------------------------


def test_read_catalog_entries_whole_episode_is_one_row_with_two_decisions(catalog_db: Path) -> None:
    seed_whole_episode(catalog_db)
    rows = _entries(catalog_db)
    assert len(rows) == 1
    assert rows[0].decisions == (
        DecisionRecord(
            target_id=TargetId("072A"), rule_name="numero_nu_confirmed", tier=DecisionTier.DOWNLOAD
        ),
        DecisionRecord(
            target_id=TargetId("072B"), rule_name="numero_nu_confirmed", tier=DecisionTier.DOWNLOAD
        ),
    )
    assert rows[0].decisions[0].tier is DecisionTier.DOWNLOAD


@pytest.mark.parametrize("target_id", [TargetId("072A"), TargetId("072B")])
def test_read_catalog_entries_filter_by_one_target_returns_whole_episode(
    catalog_db: Path, target_id: TargetId
) -> None:
    seed_whole_episode(catalog_db)
    rows = _entries(catalog_db, target_id=target_id)
    assert len(rows) == 1
    assert [d.target_id for d in rows[0].decisions] == ["072A", "072B"]


def test_read_catalog_entries_unmatched_file_has_empty_decisions(catalog_db: Path) -> None:
    _seed_unmatched(catalog_db)
    [row] = _entries(catalog_db)
    assert row.decisions == ()


def test_read_matched_and_total_file_counts_whole_episode_counts_as_one_file(
    catalog_db: Path,
) -> None:
    seed_whole_episode(catalog_db)
    matched, total = _counts(catalog_db)
    assert (matched, total) == (1, 1)


# ---------------------------------------------------------------------------
# Tests: file history
# ---------------------------------------------------------------------------


def _history(
    catalog_db: Path, native_id: str, *, since: datetime = _EPOCH, until: datetime = _YEAR_3000
) -> FileHistory | None:
    with ThreadReadConnections(catalog_db, open_reader) as thread_read_connections:
        reader = SqliteCatalogFileReader(thread_read_connections)
        return reader.read_file_history(file_id(native_id), since=since, until=until)


def test_file_history_carries_observations_and_dated_decisions(catalog_db: Path) -> None:
    seed(catalog_db)
    file_history = _history(catalog_db, "a" * 32)
    assert file_history is not None
    assert file_history.file == FileKey(network=Network.ED2K, native_id="a" * 32)
    assert file_history.size_bytes == 100
    assert file_history.decisions == (
        DatedDecision(
            file=FileKey(network=Network.ED2K, native_id="a" * 32),
            decision=DecisionRecord(
                target_id=TargetId("062A"), rule_name="id_segment_exact", tier=DecisionTier.DOWNLOAD
            ),
            decided_at=datetime(2026, 6, 22, 10, 0, 1, tzinfo=UTC),
            node_id=NodeId("n1"),
        ),
    )
    assert file_history.decisions[0].decision.tier is DecisionTier.DOWNLOAD
    assert [o.reported_file.filename for o in file_history.observations] == ["keroro_062.avi"]
    assert file_history.latest_observation == file_history.observations[0]
    assert file_history.known_filenames == ("keroro_062.avi",)


def test_file_history_reads_its_observations_in_the_window_and_its_latest_in_any(
    catalog_db: Path,
) -> None:
    seed(catalog_db)
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_observation(
            connection, "a" * 32, "older.avi", observed_at="2026-06-21T10:00:00+00:00"
        )
    since, until = datetime(2026, 6, 1, tzinfo=UTC), datetime.fromisoformat(SEEN_AT)
    file_history = _history(catalog_db, "a" * 32, since=since, until=until)
    assert file_history is not None
    assert [o.reported_file.filename for o in file_history.observations] == ["older.avi"]
    assert file_history.latest_observation is not None
    assert file_history.latest_observation.reported_file.filename == "keroro_062.avi"


def test_file_history_of_an_unknown_file_id_is_none(catalog_db: Path) -> None:
    seed(catalog_db)
    assert _history(catalog_db, "f" * 32) is None
    with ThreadReadConnections(catalog_db, open_reader) as thread_read_connections:
        reader = SqliteCatalogFileReader(thread_read_connections)
        by_native_id = reader.read_file_history(
            FileId(bytes.fromhex("a" * 32)), since=_EPOCH, until=_YEAR_3000
        )
    assert by_native_id is None  # a file is read by its id, never by its ed2k hash


def test_file_history_reads_a_recorded_decision_back_to_the_microsecond(catalog_db: Path) -> None:
    decided = DatedDecision(
        file=FileKey(network=Network.ED2K, native_id="a" * 32),
        decision=DecisionRecord(
            target_id=TargetId("062A"), rule_name="id_segment_exact", tier=DecisionTier.DOWNLOAD
        ),
        decided_at=datetime(2026, 6, 22, 10, 0, 1, 123456, tzinfo=UTC),
        node_id=NodeId("n1"),
    )
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, "a" * 32)
        SqliteDecisionStore(connection).record_decision(decided)
    file_history = _history(catalog_db, "a" * 32)
    assert file_history is not None
    assert file_history.decisions == (decided,)


def test_file_history_retracted_target_is_no_decision(catalog_db: Path) -> None:
    """A file whose LATEST decision is the crawler's retraction sentinel exposes NO decision
    from ``read_file_history``, identical to an unmatched file (spec §9). The earlier
    (pre-retraction) real decision must not leak through."""
    seed_retracted(catalog_db)
    file_history = _history(catalog_db, "c" * 32)
    assert file_history is not None
    assert file_history.decisions == ()


def test_file_history_no_decision(catalog_db: Path) -> None:
    """Detail works even without a decision (unmatched file)."""
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, "b" * 32, 200)
        insert_observation(
            connection,
            "b" * 32,
            "unknown.avi",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=200,
        )
    file_history = _history(catalog_db, "b" * 32)
    assert file_history is not None
    assert file_history.decisions == ()
    assert file_history.size_bytes == 200


def test_file_history_whole_episode_lists_both_decisions(catalog_db: Path) -> None:
    seed_whole_episode(catalog_db)
    file_history = _history(catalog_db, "a" * 32)
    assert file_history is not None
    assert [d.decision.target_id for d in file_history.decisions] == ["072A", "072B"]


# ---------------------------------------------------------------------------
# Tests: read_catalog_entries with multiple combined filters
# ---------------------------------------------------------------------------


def test_read_catalog_entries_combined_target_and_tier_filters(catalog_db: Path) -> None:
    seed(catalog_db)
    hit = _entries(catalog_db, target_id=TargetId("062A"), tier=DecisionTier.DOWNLOAD)
    miss = _entries(catalog_db, target_id=TargetId("062A"), tier=DecisionTier.NOTIFY)
    assert len(hit) == 1
    assert miss == ()


def test_read_catalog_entries_reads_at_most_its_limit_from_its_offset(catalog_db: Path) -> None:
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        for n in range(_LIMIT + 2):
            insert_file(connection, f"{n:032x}", size_bytes=n)
    first = _entries(catalog_db, sort=CatalogEntrySort.SIZE, direction=SortDirection.ASC)
    second = _entries(
        catalog_db, sort=CatalogEntrySort.SIZE, direction=SortDirection.ASC, offset=_LIMIT
    )
    assert [catalog_entry.size_bytes for catalog_entry in first] == list(range(_LIMIT))
    assert [catalog_entry.size_bytes for catalog_entry in second] == [_LIMIT, _LIMIT + 1]


def test_file_history_observations_include_media_fields_none(catalog_db: Path) -> None:
    """An observation's duration_seconds and bitrate_kbps are None when the network gave none."""
    seed(catalog_db)
    file_history = _history(catalog_db, "a" * 32)
    assert file_history is not None
    assert len(file_history.observations) == 1
    obs = file_history.observations[0].reported_file
    assert obs.duration_seconds is None
    assert obs.bitrate_kbps is None


def test_file_history_observations_include_media_fields_present(catalog_db: Path) -> None:
    """An observation's duration_seconds and bitrate_kbps are filled when present."""
    h = "d" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, h, 150)
        insert_observation(
            connection,
            h,
            "keroro_media.avi",
            size_bytes=150,
            source_count=3,
            duration_seconds=1320,
            bitrate_kbps=192,
        )
    file_history = _history(catalog_db, h)
    assert file_history is not None
    assert len(file_history.observations) == 1
    obs = file_history.observations[0].reported_file
    assert obs.duration_seconds == 1320
    assert obs.bitrate_kbps == 192


def _seed_unmatched(db: Path) -> None:
    """Add a second file (b*32) with an observation but NO match decision."""
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, "b" * 32, 200)
        insert_observation(
            connection,
            "b" * 32,
            "gallego_ep021.ogm",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=200,
        )


def test_read_catalog_entries_matched_only_excludes_unmatched(catalog_db: Path) -> None:
    seed(catalog_db)
    _seed_unmatched(catalog_db)
    rows = _entries(catalog_db, matched_only=True)
    hashes = {r.file.native_id for r in rows}
    assert hashes == {"a" * 32}  # only the matched file


def test_read_catalog_entries_matched_only_excludes_retracted(catalog_db: Path) -> None:
    """A file whose latest decision is a retraction is NOT matched, even though its
    ``target_id`` column is non-NULL (the crawler's sentinel is an empty string, not NULL)."""
    seed(catalog_db)
    seed_retracted(catalog_db)
    rows = _entries(catalog_db, matched_only=True)
    hashes = {r.file.native_id for r in rows}
    assert hashes == {"a" * 32}  # the retracted file ("c"*32) is excluded


def test_read_catalog_entries_lists_a_retracted_file_with_no_decision(catalog_db: Path) -> None:
    seed_retracted(catalog_db)
    [row] = _entries(catalog_db)
    assert row.decisions == ()


def test_read_catalog_entries_default_includes_unmatched(catalog_db: Path) -> None:
    seed(catalog_db)
    _seed_unmatched(catalog_db)
    rows = _entries(catalog_db)
    hashes = {r.file.native_id for r in rows}
    assert hashes == {"a" * 32, "b" * 32}  # default matched_only=False → both


def test_read_catalog_entries_shows_latest_observation(catalog_db: Path) -> None:
    """Same hash with two observations → read_catalog_entries returns the most recent filename."""
    h = "c" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, h, 300)
        insert_observation(
            connection,
            h,
            "old_name.avi",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=300,
        )
        insert_observation(
            connection,
            h,
            "new_name.avi",
            observed_at="2026-06-22T12:00:00.000000+00:00",
            size_bytes=300,
            source_count=2,
        )
    rows = _entries(catalog_db)
    assert len(rows) == 1
    assert _latest_filename(rows[0]) == "new_name.avi"


# ---------------------------------------------------------------------------
# Tests: read_matched_and_total_file_counts, /files summary (matched, total)
# ---------------------------------------------------------------------------


def test_read_matched_and_total_file_counts_no_filter_returns_matched_and_total(
    catalog_db: Path,
) -> None:
    seed(catalog_db)  # 1 matched file
    _seed_unmatched(catalog_db)  # 1 unmatched file
    matched, total = _counts(catalog_db)
    assert (matched, total) == (1, 2)


def test_read_matched_and_total_file_counts_respects_search_text(catalog_db: Path) -> None:
    seed(catalog_db)  # filename keroro_062.avi (matched)
    _seed_unmatched(catalog_db)  # filename gallego_ep021.ogm (unmatched)
    matched, total = _counts(catalog_db, search_text="gallego")
    assert (matched, total) == (0, 1)  # only the unmatched file matches the search text


def test_read_matched_and_total_file_counts_counts_retracted_as_unmatched(catalog_db: Path) -> None:
    """A retracted file counts toward ``total`` but not ``matched`` (the matched count is
    unchanged by its presence, even though its ``target_id`` column is non-NULL)."""
    seed(catalog_db)  # 1 matched file
    seed_retracted(catalog_db)  # 1 retracted (== unmatched) file
    matched, total = _counts(catalog_db)
    assert (matched, total) == (1, 2)


def test_read_matched_and_total_file_counts_empty_catalogue_matched_is_zero_not_none(
    catalog_db: Path,
) -> None:
    """Regression guard for the COUNT → SUM(CASE ...) rewrite: SUM over zero rows is NULL in
    SQL, unlike COUNT which is 0. An empty catalogue must still report ``matched == 0``."""
    matched, total = _counts(catalog_db)
    assert (matched, total) == (0, 0)


# ---------------------------------------------------------------------------
# Tests: target-scoped read excludes catalog-tier (catch-all pinned to 001A)
# ---------------------------------------------------------------------------


def _seed_catalog_tier_on_001a(db: Path) -> None:
    """A keroro_large catch-all file: its only decision is tier 'catalog' pinned to 001A."""
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, "b" * 32, 50)
        insert_observation(
            connection,
            "b" * 32,
            "keroro manga.zip",
            observed_at="2026-07-01T10:00:00.000000+00:00",
            size_bytes=50,
        )
        insert_decision(
            connection,
            "b" * 32,
            "001A",
            "catalog",
            rule_name="keroro_large",
            decided_at="2026-07-01T10:00:01.000000+00:00",
        )


def test_target_scope_excludes_catalog_tier(catalog_db: Path) -> None:
    """A catalog-tier decision pinned to 001A must NOT surface under target='001A'."""
    _seed_catalog_tier_on_001a(catalog_db)
    rows = _entries(catalog_db, target_id=TargetId("001A"))
    assert rows == ()
    matched, _total = _counts(catalog_db, target_id=TargetId("001A"))
    assert matched == 0


def test_target_scope_keeps_non_catalog_tier(catalog_db: Path) -> None:
    """A non-catalog (download) decision on 062A is still returned under target='062A'."""
    seed(catalog_db)  # existing helper: a 'download' decision on 062A
    rows = _entries(catalog_db, target_id=TargetId("062A"))
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Tests: sortable read_catalog_entries via the fixed column allowlist + best_tier_rank
# ---------------------------------------------------------------------------


def _seed_sortable(db: Path) -> None:
    """Three single-decision files with distinct sort keys and one decision each at a distinct
    tier (download > notify > catalog), for the sort-order tests.

    hash 'a': beta.avi  size 300 sources  5 seen 2026-01-01 tier notify   (062A)
    hash 'b': alpha.avi size 100 sources 15 seen 2026-01-02 tier download (072A)
    hash 'c': gamma.avi size 200 sources 10 seen 2026-01-03 tier catalog  (keroro_large)

    Every sort key yields a distinct order, and ``last_seen`` (a < b < c) is deliberately
    orthogonal to BOTH ``size`` (a is largest) AND ``tier`` (b is strongest): so a sort column
    that silently swaps to ``observed_at_micros`` cannot pass unnoticed on any key, including
    ``tier``.
    """
    rows = [
        ("a" * 32, "beta.avi", 300, 5, "2026-01-01T10:00:00.000000+00:00", "062A", "notify"),
        ("b" * 32, "alpha.avi", 100, 15, "2026-01-02T10:00:00.000000+00:00", "072A", "download"),
        ("c" * 32, "gamma.avi", 200, 10, "2026-01-03T10:00:00.000000+00:00", "001A", "catalog"),
    ]
    with closing(sqlite3.connect(db)) as connection, connection:
        for h, name, size, sources, seen, tid, tier in rows:
            insert_file(connection, h, size)
            insert_observation(
                connection, h, name, observed_at=seen, size_bytes=size, source_count=sources
            )
            insert_decision(connection, h, tid, tier, decided_at="2026-01-04T10:00:00.000000+00:00")


def _hashes(rows: tuple[CatalogEntry, ...]) -> list[str]:
    return [r.file.native_id for r in rows]


@pytest.mark.parametrize(
    ("sort", "direction", "expected"),
    [
        ("name", "asc", ["b", "a", "c"]),  # alpha, beta, gamma
        ("name", "desc", ["c", "a", "b"]),
        ("size", "asc", ["b", "c", "a"]),  # 100, 200, 300
        ("size", "desc", ["a", "c", "b"]),
        ("sources", "asc", ["a", "c", "b"]),  # 5, 10, 15
        ("sources", "desc", ["b", "c", "a"]),
        ("last_seen", "desc", ["c", "b", "a"]),  # 01-03, 01-02, 01-01 (the default)
        ("last_seen", "asc", ["a", "b", "c"]),
        ("tier", "desc", ["b", "a", "c"]),  # download(2), notify(1), catalog(0)
        ("tier", "asc", ["c", "a", "b"]),
    ],
)
def test_read_catalog_entries_sort_orders(
    catalog_db: Path, sort: str, direction: str, expected: list[str]
) -> None:
    _seed_sortable(catalog_db)
    rows = _entries(catalog_db, sort=CatalogEntrySort(sort), direction=SortDirection(direction))
    assert _hashes(rows) == [c * 32 for c in expected]


def test_read_catalog_entries_sort_tiebreak_is_file_id(catalog_db: Path) -> None:
    """Two files with the same sort key keep a deterministic order via the file_id tiebreak."""
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        for h in ("a" * 32, "e" * 32):  # inserted a-first on purpose
            insert_file(connection, h)
            insert_observation(
                connection, h, "same.avi", observed_at="2026-01-01T10:00:00.000000+00:00"
            )
    rows = _entries(catalog_db, sort=CatalogEntrySort.SIZE, direction=SortDirection.ASC)
    assert _hashes(rows) == ["e" * 32, "a" * 32]  # e's file_id sorts first


def test_tier_rank_case_matches_tier_rank() -> None:
    """The generated CASE maps every tier to its ``DecisionTier.rank``."""
    sql = _tier_rank_case("ld.tier")
    for tier in DecisionTier:
        assert f"WHEN '{tier}' THEN {tier.rank}" in sql


def test_every_sort_has_its_column() -> None:
    assert set(SORT_COLUMNS) == set(CatalogEntrySort)


# ---------------------------------------------------------------------------
# Tests: read_file_count_by_tier, the tier facet's live counts (spec §3.3)
# ---------------------------------------------------------------------------


def _seed_mixed_tier_file(db: Path) -> None:
    """One file with TWO current decisions in DIFFERENT tiers (download + notify): it must count
    under both facets."""
    h = "d" * 32
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, h)
        insert_observation(
            connection, h, "mixed.avi", observed_at="2026-01-01T10:00:00.000000+00:00"
        )
        for tid, tier in (("062A", "download"), ("062B", "notify")):
            insert_decision(connection, h, tid, tier, decided_at="2026-01-02T10:00:00.000000+00:00")


def test_read_file_count_by_tier_groups_by_tier(catalog_db: Path) -> None:
    _seed_sortable(catalog_db)  # one file per tier
    counts = _read_file_count_by_tier(catalog_db)
    assert counts == {DecisionTier.DOWNLOAD: 1, DecisionTier.NOTIFY: 1, DecisionTier.CATALOG: 1}


def test_read_file_count_by_tier_keys_each_count_by_the_type(catalog_db: Path) -> None:
    _seed_sortable(catalog_db)
    assert {type(tier) for tier in _read_file_count_by_tier(catalog_db)} == {DecisionTier}


def test_read_file_count_by_tier_empty_catalogue_is_empty(catalog_db: Path) -> None:
    counts = _read_file_count_by_tier(catalog_db)
    assert counts == {}


def test_read_file_count_by_tier_multi_tier_file_counts_in_both(catalog_db: Path) -> None:
    _seed_mixed_tier_file(catalog_db)
    counts = _read_file_count_by_tier(catalog_db)
    assert counts == {DecisionTier.DOWNLOAD: 1, DecisionTier.NOTIFY: 1}


def test_read_file_count_by_tier_respects_search_text(catalog_db: Path) -> None:
    """The facet honours the OTHER filters (here ``search_text``): only alpha.avi matches."""
    _seed_sortable(catalog_db)
    counts = _read_file_count_by_tier(catalog_db, search_text="alpha")
    assert counts == {DecisionTier.DOWNLOAD: 1}


# ---------------------------------------------------------------------------
# Files with no observation / tied observations
# ---------------------------------------------------------------------------


def _seed_file_without_observation(db: Path) -> str:
    """A file with NO observation at all (a file row is written before its first observation is
    recorded). Returns its hash."""
    h = "d" * 32
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, h, 42)
    return h


def test_read_catalog_entries_lists_file_with_no_observation(catalog_db: Path) -> None:
    """A file with no observation is still listed, with none.

    This is THE case where the two shapes of ``latest_obs`` differ internally: the seek form
    yields a row of NULLs for such a file, the older window form yielded no row at all. Both
    reach the same result only because every consumer LEFT JOINs it onto ``files``, so
    this pins that the difference stays absorbed.
    """
    h = _seed_file_without_observation(catalog_db)
    rows = _entries(catalog_db)
    assert [row.file.native_id for row in rows] == [h]
    assert rows[0].latest_observation is None


def test_read_matched_and_total_file_counts_counts_file_with_no_observation(
    catalog_db: Path,
) -> None:
    """It counts in ``total`` (it is a catalogued file) but not in ``matched`` (no decision)."""
    _seed_file_without_observation(catalog_db)
    matched, total = _counts(catalog_db)
    assert (matched, total) == (0, 1)


def test_read_catalog_entries_search_text_filter_excludes_file_with_no_observation(
    catalog_db: Path,
) -> None:
    """No observation means no filename to match: ``NULL LIKE ?`` is NULL, so the row drops."""
    _seed_file_without_observation(catalog_db)
    rows = _entries(catalog_db, search_text="keroro")
    assert rows == ()


def test_read_catalog_entries_observation_tie_break_on_the_newest_variant(catalog_db: Path) -> None:
    """Two observations at the SAME ``observed_at``: the higher ``variant_id`` wins (D4)."""
    h = "a" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, h)
        for name in ("first.avi", "second.avi"):  # same instant, ascending variant ids
            insert_observation(connection, h, name, observed_at="2026-07-03T10:00:00.000000+00:00")
    rows = _entries(catalog_db)
    assert _latest_filename(rows[0]) == "second.avi"


def test_file_history_of_a_file_never_seen_has_no_observation(catalog_db: Path) -> None:
    h = _seed_file_without_observation(catalog_db)
    file_history = _history(catalog_db, h)
    assert file_history is not None
    assert (
        file_history.observations,
        file_history.latest_observation,
        file_history.known_filenames,
    ) == (
        (),
        None,
        (),
    )


# ---------------------------------------------------------------------------
# Read-path shape (performance is a correctness property here)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "sql"),
    [
        ("latest_observation alone", _SQL_CTES + LATEST_OBSERVATION_PROBE),
        (
            "read_catalog_entries",
            _SQL_LIST_FILES_BASE + "ORDER BY obs.observed_at_micros DESC LIMIT 50",
        ),
        (
            "read_matched_and_total_file_counts",
            _SQL_COUNT_FILES_BASE + _JOIN_LATEST_OBSERVATION + _JOIN_DECISIONS,
        ),
        (
            "read_file_count_by_tier",
            _SQL_TIER_COUNTS_BASE + _JOIN_LATEST_OBSERVATION + "GROUP BY ld.tier",
        ),
    ],
    ids=[
        "latest_observation alone",
        "read_catalog_entries",
        "read_matched_and_total_file_counts",
        "read_file_count_by_tier",
    ],
)
def test_latest_obs_seeks_per_file_instead_of_scanning_observations(
    catalog_db: Path, label: str, sql: str
) -> None:
    """Every /files query reading the latest observation SEEKS each variant's observations by
    primary key, never walks ``observations`` (11.6M rows on the node). Asserts the PLAN, not a
    duration, so it stays deterministic; each real query is checked, not the CTE alone."""
    with closing(open_reader(catalog_db)) as reader:
        plan = [str(step["detail"]) for step in rows(reader, "EXPLAIN QUERY PLAN " + sql)]

    assert any(re.match(r"SEARCH o\w* USING PRIMARY KEY \(variant_id=\?", step) for step in plan), (
        f"{label} does not seek observations by key: {plan}"
    )
    assert not any(step.startswith("SCAN o") for step in plan), f"{label} scans: {plan}"


class FileCounter(Protocol):
    def __call__(
        self, reader: SqliteCatalogFileReader, /, *, search_text: str | None
    ) -> object: ...


_COUNTERS: dict[str, FileCounter] = {
    "read_matched_and_total_file_counts": lambda reader, search_text: (
        reader.read_matched_and_total_file_counts(
            target_id=None, tier=None, search_text=search_text
        )
    ),
    "read_file_count_by_tier": lambda reader, search_text: reader.read_file_count_by_tier(
        target_id=None, search_text=search_text
    ),
}


@pytest.mark.parametrize("counter", sorted(_COUNTERS))
@pytest.mark.parametrize("search_text", [None, "keroro"])
def test_counters_read_observations_only_for_a_name_filter(
    catalog_db: Path, counter: str, search_text: str | None
) -> None:
    """The default /files page counts without a per-file latest observation (D18)."""
    tables: set[str] = set()

    def record(action: int, table: str | None, *_: str | None) -> int:  # noqa: PLR0917
        if action == sqlite3.SQLITE_READ and table is not None:
            tables.add(table)
        return sqlite3.SQLITE_OK

    with ThreadReadConnections(catalog_db, open_reader) as thread_read_connections:
        thread_read_connections.connection().set_authorizer(record)
        _COUNTERS[counter](
            SqliteCatalogFileReader(thread_read_connections), search_text=search_text
        )
    assert ("observations" in tables) is (search_text is not None)
