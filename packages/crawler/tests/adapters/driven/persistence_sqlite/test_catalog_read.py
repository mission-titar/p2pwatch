"""TDD tests for the catalog's readers: coverage, filtered explorer, detail (spec W-D6 / §6)."""

import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from catalog_matching.domain.config import TIER_RANK
from catalog_matching.domain.engine import DecisionRecord
from p2pwatch.adapters.driven.persistence_sqlite.catalog_read import (
    _JOIN_DECISIONS,
    _JOIN_LATEST_OBSERVATION,
    _SQL_COUNT_FILES_BASE,
    _SQL_CTES,
    _SQL_LIST_FILES_BASE,
    _SQL_TIER_COUNTS_BASE,
    PAGE_SIZE,
    SORT_COLUMNS,
    CatalogReader,
    SqliteCatalogFileReader,
    SqliteCoverageReader,
    SqliteSourceReader,
    _tier_rank_case,
)
from p2pwatch.adapters.driven.persistence_sqlite.reader import ReaderProvider, open_reader
from p2pwatch.adapters.driving.webui.views import (
    NameDetail,
    SourceDetail,
    SourceFilePeriod,
    SourceRow,
)
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import DatedDecision, FileHistory
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey, SourceRole
from p2pwatch_testing.catalog_rows import (
    SEEN_AT,
    file_id,
    insert_decision,
    insert_file,
    insert_observation,
    insert_source,
    insert_source_point,
    insert_source_variant,
    source_id,
)

pytestmark = pytest.mark.usefixtures("close_test_connections")

# Selects the CTE under test on its own: SQLite drops the CTEs a query does not reference, so
# the resulting plan is exactly how ``latest_observation`` is resolved.
LATEST_OBSERVATION_PROBE = (
    "SELECT file_id, filename, source_count, observed_at FROM latest_observation"
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_YEAR_3000 = datetime(3000, 1, 1, tzinfo=UTC)  # after every instant a test writes
_LIMIT = 50


def _entries(
    catalog_db: Path,
    *,
    target_id: str | None = None,
    tier: str | None = None,
    search_text: str | None = None,
    matched_only: bool = False,
    sort: CatalogEntrySort = CatalogEntrySort.LAST_SEEN,
    direction: SortDirection = SortDirection.DESC,
    offset: int = 0,
) -> tuple[CatalogEntry, ...]:
    return SqliteCatalogFileReader(ReaderProvider(catalog_db)).read_catalog_entries(
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
    target_id: str | None = None,
    tier: str | None = None,
    search_text: str | None = None,
) -> tuple[int, int]:
    return SqliteCatalogFileReader(ReaderProvider(catalog_db)).read_matched_and_total_file_counts(
        target_id=target_id, tier=tier, search_text=search_text
    )


def _tier_counts(catalog_db: Path, *, search_text: str | None = None) -> Mapping[str, int]:
    return SqliteCatalogFileReader(ReaderProvider(catalog_db)).read_file_count_by_tier(
        target_id=None, search_text=search_text
    )


def _latest_filename(entry: CatalogEntry) -> str | None:
    observation = entry.latest_observation
    return None if observation is None else observation.reported_file.filename


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed(db: Path) -> None:
    """Populate the database with a file, an observation, a decision."""
    with sqlite3.connect(db) as conn:
        insert_file(conn, "a" * 32)
        insert_observation(conn, "a" * 32, "keroro_062.avi", source_count=5)
        insert_decision(
            conn,
            "a" * 32,
            "062A",
            "download",
            rule_name="id_segment_exact",
            decided_at="2026-06-22T10:00:01.000000+00:00",
        )


def _seed_whole_episode(db: Path) -> None:
    """A single whole-episode file (hash a*32) satisfying BOTH segments 072A + 072B (two
    current decisions at tier ``download``): the core multi-target fixture (spec §9).
    Standalone: never combine with ``_seed`` (same hash)."""
    h = "a" * 32
    with sqlite3.connect(db) as conn:
        insert_file(conn, h, 170_000_000)
        insert_observation(
            conn,
            h,
            "keroro_072.avi",
            observed_at="2026-07-01T10:00:00.000000+00:00",
            size_bytes=170_000_000,
            source_count=7,
        )
        for tid in ("072A", "072B"):
            insert_decision(
                conn,
                h,
                tid,
                "download",
                rule_name="numero_nu_confirmed",
                decided_at="2026-07-01T10:00:01.000000+00:00",
            )


# ---------------------------------------------------------------------------
# Tests: coverage
# ---------------------------------------------------------------------------


def _read_target_coverage(catalog_db: Path) -> Mapping[str, tuple[str, ...]]:
    return SqliteCoverageReader(ReaderProvider(catalog_db)).read_target_coverage()


def test_target_coverage_groups_by_target(catalog_db: Path) -> None:
    _seed(catalog_db)
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)


def test_target_coverage_empty_db_returns_empty(catalog_db: Path) -> None:
    coverage = _read_target_coverage(catalog_db)
    assert coverage == {}


def test_target_coverage_multiple_files_same_target(catalog_db: Path) -> None:
    """Two files matching the same target_id → two tiers."""
    with sqlite3.connect(catalog_db) as conn:
        for suffix in ("a", "b"):
            insert_file(conn, suffix * 32)
            insert_decision(conn, suffix * 32, "062A", "download")
    coverage = _read_target_coverage(catalog_db)
    assert len(coverage["062A"]) == 2


def test_target_coverage_whole_episode_contributes_to_both_targets(catalog_db: Path) -> None:
    _seed_whole_episode(catalog_db)
    coverage = _read_target_coverage(catalog_db)
    assert coverage["072A"] == ("download",)
    assert coverage["072B"] == ("download",)


def test_target_coverage_ignores_legacy_empty_target_sentinel(catalog_db: Path) -> None:
    h = "e" * 32
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, h)
        insert_decision(
            conn,
            h,
            "090A",
            "download",
            rule_name="id_segment_exact",
            decided_at="2026-07-05T10:00:00.000000+00:00",
        )
        insert_decision(
            conn, h, "", "retracted", rule_name="", decided_at="2026-07-05T11:00:00.000000+00:00"
        )
    coverage = _read_target_coverage(catalog_db)
    assert coverage["090A"] == ("download",)
    assert "" not in coverage


# ---------------------------------------------------------------------------
# Tests: explorer, filters present / absent
# ---------------------------------------------------------------------------


def test_list_files_no_filter_returns_all(catalog_db: Path) -> None:
    _seed(catalog_db)
    rows = _entries(catalog_db)
    assert rows == (
        CatalogEntry(
            file=FileKey(Network.ED2K, "a" * 32),
            size_bytes=100,
            latest_observation=FileObservation(
                ReportedFile(
                    FileKey(Network.ED2K, "a" * 32), "keroro_062.avi", 100, 5, keyword="keroro"
                ),
                observed_at=datetime(2026, 6, 22, 10, tzinfo=UTC),
            ),
            decisions=(DecisionRecord("062A", "id_segment_exact", "download"),),
        ),
    )


def test_list_files_filter_by_target(catalog_db: Path) -> None:
    _seed(catalog_db)
    hit = _entries(catalog_db, target_id="062A")
    miss = _entries(catalog_db, target_id="001A")
    assert len(hit) == 1
    assert miss == ()


def test_list_files_filter_by_tier(catalog_db: Path) -> None:
    _seed(catalog_db)
    hit = _entries(catalog_db, tier="download")
    miss = _entries(catalog_db, tier="notify")
    assert len(hit) == 1
    assert miss == ()


def test_list_files_filter_by_query(catalog_db: Path) -> None:
    _seed(catalog_db)
    hit = _entries(catalog_db, search_text="keroro")
    miss = _entries(catalog_db, search_text="unknown")
    assert len(hit) == 1
    assert miss == ()


def test_list_files_reads_none_past_the_offset(catalog_db: Path) -> None:
    _seed(catalog_db)
    assert _entries(catalog_db, offset=1) == ()


# ---------------------------------------------------------------------------
# Tests: list_files / count_files: one row per file, decisions aggregated (spec §9)
# ---------------------------------------------------------------------------


def test_list_files_whole_episode_is_one_row_with_two_decisions(catalog_db: Path) -> None:
    _seed_whole_episode(catalog_db)
    rows = _entries(catalog_db)
    assert len(rows) == 1
    assert rows[0].decisions == (
        DecisionRecord("072A", "numero_nu_confirmed", "download"),
        DecisionRecord("072B", "numero_nu_confirmed", "download"),
    )


@pytest.mark.parametrize("target_id", ["072A", "072B"])
def test_list_files_filter_by_one_target_returns_whole_episode(
    catalog_db: Path, target_id: str
) -> None:
    _seed_whole_episode(catalog_db)
    rows = _entries(catalog_db, target_id=target_id)
    assert len(rows) == 1
    assert [d.target_id for d in rows[0].decisions] == ["072A", "072B"]


def test_list_files_unmatched_file_has_empty_decisions(catalog_db: Path) -> None:
    _seed_unmatched(catalog_db)
    [row] = _entries(catalog_db)
    assert row.decisions == ()


def test_count_files_whole_episode_counts_as_one_file(catalog_db: Path) -> None:
    _seed_whole_episode(catalog_db)
    matched, total = _counts(catalog_db)
    assert (matched, total) == (1, 1)


# ---------------------------------------------------------------------------
# Tests: detail
# ---------------------------------------------------------------------------


def _history(
    catalog_db: Path, native_id: str, *, since: datetime = _EPOCH, until: datetime = _YEAR_3000
) -> FileHistory | None:
    reader = SqliteCatalogFileReader(ReaderProvider(catalog_db))
    return reader.read_file_history(file_id(native_id), since=since, until=until)


def test_file_history_carries_observations_and_dated_decisions(catalog_db: Path) -> None:
    _seed(catalog_db)
    detail = _history(catalog_db, "a" * 32)
    assert detail is not None
    assert detail.file == FileKey(Network.ED2K, "a" * 32)
    assert detail.size_bytes == 100
    assert detail.decisions == (
        DatedDecision(
            DecisionRecord(target_id="062A", rule_name="id_segment_exact", tier="download"),
            decided_at=datetime(2026, 6, 22, 10, 0, 1, tzinfo=UTC),
            node_id="n1",
        ),
    )
    assert [o.reported_file.filename for o in detail.observations] == ["keroro_062.avi"]
    assert detail.latest_observation == detail.observations[0]
    assert detail.known_filenames == ("keroro_062.avi",)


def test_file_history_reads_its_observations_in_the_window_and_its_latest_in_any(
    catalog_db: Path,
) -> None:
    _seed(catalog_db)
    with sqlite3.connect(catalog_db) as conn:
        insert_observation(conn, "a" * 32, "older.avi", observed_at="2026-06-21T10:00:00+00:00")
    since, until = datetime(2026, 6, 1, tzinfo=UTC), datetime.fromisoformat(SEEN_AT)
    detail = _history(catalog_db, "a" * 32, since=since, until=until)
    assert detail is not None
    assert [o.reported_file.filename for o in detail.observations] == ["older.avi"]
    assert detail.latest_observation is not None
    assert detail.latest_observation.reported_file.filename == "keroro_062.avi"


def test_file_history_of_an_unknown_file_id_is_none(catalog_db: Path) -> None:
    _seed(catalog_db)
    assert _history(catalog_db, "f" * 32) is None
    reader = SqliteCatalogFileReader(ReaderProvider(catalog_db))
    by_native_id = reader.read_file_history(bytes.fromhex("a" * 32), since=_EPOCH, until=_YEAR_3000)
    assert by_native_id is None  # a file is read by its id, never by its ed2k hash


def test_file_history_retracted_target_is_no_decision(catalog_db: Path) -> None:
    """A file whose LATEST decision is the crawler's retraction sentinel exposes NO decision
    from ``read_file_history``, identical to an unmatched file (spec §9). The earlier
    (pre-retraction) real decision must not leak through."""
    _seed_retracted(catalog_db)
    detail = _history(catalog_db, "c" * 32)
    assert detail is not None
    assert detail.decisions == ()


def test_file_history_no_decision(catalog_db: Path) -> None:
    """Detail works even without a decision (unmatched file)."""
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, "b" * 32, 200)
        insert_observation(
            conn,
            "b" * 32,
            "unknown.avi",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=200,
        )
    detail = _history(catalog_db, "b" * 32)
    assert detail is not None
    assert detail.decisions == ()
    assert detail.size_bytes == 200


def test_file_history_whole_episode_lists_both_decisions(catalog_db: Path) -> None:
    _seed_whole_episode(catalog_db)
    detail = _history(catalog_db, "a" * 32)
    assert detail is not None
    assert [d.decision.target_id for d in detail.decisions] == ["072A", "072B"]


# ---------------------------------------------------------------------------
# Tests: a file's source history as periods (source points spec, D6)
# ---------------------------------------------------------------------------

_USER = "1f2e" * 8
_S = 1_000_000  # a second in microseconds


def _at(micros: int) -> datetime:
    return _EPOCH + timedelta(microseconds=micros)


def _micros(at: datetime) -> int:
    return (at - _EPOCH) // timedelta(microseconds=1)


_WINDOW = PeriodWindow(since=_EPOCH, until=_at(100_000 * _S), gap=timedelta(seconds=90))

# (role, observed_at, session_received_bytes) of one source's points on file a, a variant per role.
_Points = Sequence[tuple[str, int, int]]


def _seed_points(db: Path, points: _Points) -> None:
    with sqlite3.connect(db) as conn:
        insert_file(conn, "a" * 32)
        insert_source(conn, _USER)
        variants: dict[str, int] = {}
        for role, observed_at, counter in points:
            if role not in variants:
                variants[role] = insert_source_variant(conn, "a" * 32, _USER, role=role)
            insert_source_point(conn, variants[role], observed_at, session_received_bytes=counter)


def _periods(db: Path, window: PeriodWindow = _WINDOW) -> list[tuple[str, int, int, int]]:
    """``(role, first_seen_at, last_seen_at, received_bytes)`` of file a's periods, in micros."""
    reader = SqliteSourceReader(ReaderProvider(db))
    periods = reader.read_sharing_periods(FileKey(Network.ED2K, "a" * 32), window)
    return [
        (p.role.value, _micros(p.first_seen_at), _micros(p.last_seen_at), p.received_bytes)
        for p in periods
    ]


@pytest.mark.parametrize(
    ("seconds", "periods"),
    [
        ((0, 30, 60, 600), [(600, 600), (0, 60)]),
        ((0, 30, 120), [(0, 120)]),
    ],
    ids=["past-the-tolerance", "at-the-tolerance"],
)
def test_a_gap_past_the_tolerance_cuts_a_period(
    catalog_db: Path, seconds: tuple[int, ...], periods: list[tuple[int, int]]
) -> None:
    _seed_points(catalog_db, [("queued", at * _S, 0) for at in seconds])
    assert [(first // _S, last // _S) for _, first, last, _ in _periods(catalog_db)] == periods


def test_a_gap_a_microsecond_past_the_tolerance_cuts_a_period(catalog_db: Path) -> None:
    _seed_points(catalog_db, [("queued", 0, 0), ("queued", 90 * _S + 1, 0)])
    assert len(_periods(catalog_db)) == 2


def test_a_counter_that_drops_cuts_a_period(catalog_db: Path) -> None:
    _seed_points(catalog_db, [("sending", 0, 500), ("sending", 30 * _S, 100)])
    assert _periods(catalog_db) == [("sending", 30 * _S, 30 * _S, 0), ("sending", 0, 0, 0)]


@pytest.mark.parametrize(("role", "received"), [("sending", 500), ("queued", 0)])
def test_only_a_sending_period_shows_the_counters_growth(
    catalog_db: Path, role: str, received: int
) -> None:
    _seed_points(catalog_db, [(role, 0, 400), (role, 30 * _S, 650), (role, 60 * _S, 900)])
    assert _periods(catalog_db) == [(role, 0, 60 * _S, received)]


def test_a_change_of_variant_cuts_a_period_even_when_the_variant_comes_back(
    catalog_db: Path,
) -> None:
    _seed_points(catalog_db, [("queued", 0, 0), ("sending", 30 * _S, 0), ("queued", 60 * _S, 0)])
    assert [role for role, *_ in _periods(catalog_db)] == ["queued", "sending", "queued"]


def test_a_sending_period_never_counts_the_bytes_of_a_standby_one_between(
    catalog_db: Path,
) -> None:
    # The standby counter grows with another file the source sends meanwhile.
    points = [("sending", 0, 100), ("standby", 30 * _S, 600), ("sending", 60 * _S, 700)]
    _seed_points(catalog_db, points)
    assert _periods(catalog_db) == [
        ("sending", 60 * _S, 60 * _S, 0),
        ("standby", 30 * _S, 30 * _S, 0),
        ("sending", 0, 0, 0),
    ]


def test_only_the_windows_points_are_read(catalog_db: Path) -> None:
    _seed_points(catalog_db, [("queued", at * _S, 0) for at in (0, 30, 60, 90)])
    window = PeriodWindow(since=_at(30 * _S), until=_at(90 * _S), gap=_WINDOW.gap)
    assert _periods(catalog_db, window) == [("queued", 30 * _S, 60 * _S, 0)]


def test_sharing_periods_join_each_identity_on_each_node_newest_first(catalog_db: Path) -> None:
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, "a" * 32)
        insert_file(conn, "b" * 32)
        insert_source(conn, _USER)
        queued = insert_source_variant(
            conn, "a" * 32, _USER, contact_point="198.51.100.7:4661", connectable=False
        )
        elsewhere = insert_source_variant(conn, "a" * 32, _USER, node_id="n2")
        unnamed = insert_source_variant(conn, "a" * 32, None, name=None, connectable=True)
        hashless = insert_source_variant(conn, "a" * 32, None, name="Teammate")
        for variant, at in ((queued, 0), (elsewhere, 30), (queued, 60), (unnamed, 30)):
            insert_source_point(conn, variant, at * _S)
        insert_source_point(conn, hashless, 45 * _S)
        insert_source_point(conn, insert_source_variant(conn, "b" * 32, _USER), 200 * _S)
    a = FileKey(Network.ED2K, "a" * 32)
    periods = SqliteSourceReader(ReaderProvider(catalog_db)).read_sharing_periods(a, _WINDOW)
    key, queued_role = SourceKey(Network.ED2K, _USER), SourceRole.QUEUED
    at_30, at_45 = _at(30 * _S), _at(45 * _S)
    assert periods == (
        SharingPeriod(a, None, "Teammate", queued_role, None, None, at_45, at_45, 0, "n1"),
        SharingPeriod(a, None, None, queued_role, None, True, at_30, at_30, 0, "n1"),
        SharingPeriod(a, key, "AnimuseeFMR", queued_role, None, None, at_30, at_30, 0, "n2"),
        SharingPeriod(
            a,
            key,
            "AnimuseeFMR",
            queued_role,
            "198.51.100.7:4661",
            False,
            _at(0),
            _at(60 * _S),
            0,
            "n1",
        ),
    )


def test_sharing_periods_of_a_file_never_read_are_empty(catalog_db: Path) -> None:
    _seed(catalog_db)
    reader = SqliteSourceReader(ReaderProvider(catalog_db))
    assert reader.read_sharing_periods(FileKey(Network.ED2K, "a" * 32), _WINDOW) == ()


# ---------------------------------------------------------------------------
# Tests: the sources list (stage 4 spec, D13; source points spec, D6)
# ---------------------------------------------------------------------------

_OTHER = "9c0d" * 8


def _seed_sources(db: Path) -> None:
    """``_USER`` renamed on two files, then read without a name; ``_OTHER``, seen earlier."""
    with sqlite3.connect(db) as conn:
        insert_file(conn, "a" * 32)
        insert_file(conn, "b" * 32)
        insert_source(conn, _USER)
        insert_source(conn, _OTHER)
        for ed2k_hash, user, name, role, seconds in (
            ("a", _USER, "Shinobu", "queued", (10, 20)),
            ("b", _USER, "AnimuseeFMR", "queued", (30, 40)),
            ("b", _USER, None, "sending", (50, 60)),
            ("a", _OTHER, "AnimuseeFMR", "queued", (0, 5)),
            ("a", None, "x", "queued", (70, 80)),
        ):
            variant = insert_source_variant(conn, ed2k_hash * 32, user, name=name, role=role)
            for at in seconds:
                insert_source_point(conn, variant, at)


def test_list_sources_lists_each_source_once_by_last_seen_with_its_latest_name(
    catalog_db: Path,
) -> None:
    _seed_sources(catalog_db)
    rows = CatalogReader(open_reader(catalog_db)).list_sources(query=None, page=1)
    assert rows == (
        SourceRow(SourceKey(Network.ED2K, _USER), "AnimuseeFMR", 60, 2),
        SourceRow(SourceKey(Network.ED2K, _OTHER), "AnimuseeFMR", 5, 1),
    )


@pytest.mark.parametrize(
    ("query", "expected"),
    [("1F2E1F", [_USER]), ("shinob", [_USER]), ("FMR", [_USER, _OTHER]), ("2e1f", [])],
)
def test_list_sources_matches_a_hash_prefix_or_any_name_the_source_carried(
    catalog_db: Path, query: str, expected: list[str]
) -> None:
    _seed_sources(catalog_db)
    reader = CatalogReader(open_reader(catalog_db))
    rows = reader.list_sources(query=query, page=1)
    assert [row.source.native_id for row in rows] == expected
    assert reader.count_sources(query=query) == len(expected)


def test_list_sources_pages_by_fifty(catalog_db: Path) -> None:
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, "a" * 32)
        for n in range(PAGE_SIZE + 1):
            insert_source(conn, f"{n:032x}")
            insert_source_point(conn, insert_source_variant(conn, "a" * 32, f"{n:032x}"), n)
    reader = CatalogReader(open_reader(catalog_db))
    first, second = reader.list_sources(query=None, page=1), reader.list_sources(query=None, page=2)
    assert (len(first), first[0].last_seen_at) == (PAGE_SIZE, PAGE_SIZE)
    assert [row.last_seen_at for row in second] == [0]
    assert reader.count_sources(query=None) == PAGE_SIZE + 1


# ---------------------------------------------------------------------------
# Tests: the page of a source and the page of a name (stage 4 spec, D13)
# ---------------------------------------------------------------------------

_THIRD = "5a6b" * 8


def _seed_pages(db: Path) -> None:
    """``_seed_sources``, plus ``Keroro`` on ``_OTHER`` and ``_THIRD``, and a hash-less name."""
    _seed_sources(db)
    with sqlite3.connect(db) as conn:
        insert_observation(conn, "a" * 32, "keroro_062a.avi")
        insert_source(conn, _THIRD)
        for user, at in ((_OTHER, 6), (_THIRD, 8)):
            variant = insert_source_variant(conn, "a" * 32, user, name="Keroro")
            insert_source_point(conn, variant, at)
        hashless = insert_source_variant(conn, "b" * 32, None, name="AnimuseeFMR", role="standby")
        insert_source_point(conn, hashless, 95)


def _period(
    file: FileKey, source: SourceKey | None, source_name: str | None, first: int, last: int
) -> SharingPeriod:
    return SharingPeriod(
        file, source, source_name, SourceRole.QUEUED, None, None, _at(first), _at(last), 0, "n1"
    )


def test_source_detail_lists_its_names_and_its_periods_over_every_file(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    reader = CatalogReader(open_reader(catalog_db))
    detail = reader.source_detail(source_id(_USER), page=1, window=_WINDOW)
    key, a, b = (
        SourceKey(Network.ED2K, _USER),
        FileKey(Network.ED2K, "a" * 32),
        FileKey(Network.ED2K, "b" * 32),
    )
    sending = SharingPeriod(b, key, None, SourceRole.SENDING, None, None, _at(50), _at(60), 0, "n1")
    assert detail == SourceDetail(
        source=key,
        names=(SourceRow(key, "AnimuseeFMR", 40, 1), SourceRow(key, "Shinobu", 20, 1)),
        periods=(
            SourceFilePeriod(None, sending),
            SourceFilePeriod(None, _period(b, key, "AnimuseeFMR", 30, 40)),
            SourceFilePeriod("keroro_062a.avi", _period(a, key, "Shinobu", 10, 20)),
        ),
    )


def test_name_detail_lists_its_hashes_and_its_periods_without_one(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    detail = CatalogReader(open_reader(catalog_db)).name_detail(
        "AnimuseeFMR", page=1, window=_WINDOW
    )
    user, other = SourceKey(Network.ED2K, _USER), SourceKey(Network.ED2K, _OTHER)
    b = FileKey(Network.ED2K, "b" * 32)
    hashless = SharingPeriod(
        b, None, "AnimuseeFMR", SourceRole.STANDBY, None, None, _at(95), _at(95), 0, "n1"
    )
    assert detail == NameDetail(
        name="AnimuseeFMR",
        sources=(SourceRow(user, "AnimuseeFMR", 40, 1), SourceRow(other, "AnimuseeFMR", 5, 1)),
        periods=(SourceFilePeriod(None, hashless),),
    )


def test_source_detail_of_a_source_never_recorded_is_none(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    reader = CatalogReader(open_reader(catalog_db))
    assert reader.source_detail(source_id("0" * 32), page=1, window=_WINDOW) is None


def test_name_detail_of_a_name_never_recorded_is_none(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    reader = CatalogReader(open_reader(catalog_db))
    assert reader.name_detail("nobody", page=1, window=_WINDOW) is None


def test_the_pages_periods_are_read_in_the_window_only(catalog_db: Path) -> None:
    _seed_pages(catalog_db)
    reader = CatalogReader(open_reader(catalog_db))
    window = PeriodWindow(since=_at(55), until=_at(1_000), gap=_WINDOW.gap)
    source = reader.source_detail(source_id(_USER), page=1, window=window)
    name = reader.name_detail("AnimuseeFMR", page=1, window=window)
    assert source is not None and name is not None
    assert [(p.period.first_seen_at, p.period.last_seen_at) for p in source.periods] == [
        (_at(60), _at(60))
    ]
    assert [(p.period.first_seen_at, p.period.last_seen_at) for p in name.periods] == [
        (_at(95), _at(95))
    ]


# ---------------------------------------------------------------------------
# Tests: list_files with multiple combined filters
# ---------------------------------------------------------------------------


def test_list_files_combined_target_and_tier_filters(catalog_db: Path) -> None:
    _seed(catalog_db)
    hit = _entries(catalog_db, target_id="062A", tier="download")
    miss = _entries(catalog_db, target_id="062A", tier="notify")
    assert len(hit) == 1
    assert miss == ()


def test_list_files_reads_at_most_its_limit_from_its_offset(catalog_db: Path) -> None:
    with sqlite3.connect(catalog_db) as conn:
        for n in range(_LIMIT + 2):
            insert_file(conn, f"{n:032x}", size_bytes=n)
    first = _entries(catalog_db, sort=CatalogEntrySort.SIZE, direction=SortDirection.ASC)
    second = _entries(
        catalog_db, sort=CatalogEntrySort.SIZE, direction=SortDirection.ASC, offset=_LIMIT
    )
    assert [entry.size_bytes for entry in first] == list(range(_LIMIT))
    assert [entry.size_bytes for entry in second] == [_LIMIT, _LIMIT + 1]


# ---------------------------------------------------------------------------
# Tests: "latest per hash", tie-break on decided_at then id
# ---------------------------------------------------------------------------


def test_target_coverage_uses_latest_decision_per_hash(catalog_db: Path) -> None:
    """Same hash with two decisions (T1 < T2) → the coverage reads T2's tier."""
    h = "a" * 32
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, h)
        insert_decision(conn, h, "062A", "catalog")
        insert_decision(conn, h, "062A", "download", decided_at="2026-06-22T11:00:00.000000+00:00")
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)


def test_target_coverage_omits_retracted(catalog_db: Path) -> None:
    """A file whose latest decision is a retraction contributes to NO target's coverage."""
    _seed(catalog_db)
    _seed_retracted(catalog_db)
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)
    assert "063A" not in coverage  # the retracted file's earlier (now stale) target


def test_coverage_tie_break_on_id(catalog_db: Path) -> None:
    """Same hash, same decided_at, two different tiers → the larger id wins."""
    h = "b" * 32
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, h, 200)
        insert_decision(conn, h, "062A", "catalog")
        insert_decision(conn, h, "062A", "download")
    coverage = _read_target_coverage(catalog_db)
    assert coverage["062A"] == ("download",)


def test_file_history_observations_include_media_fields_none(catalog_db: Path) -> None:
    """An observation's duration_seconds and bitrate_kbps are None when the network gave none."""
    _seed(catalog_db)
    detail = _history(catalog_db, "a" * 32)
    assert detail is not None
    assert len(detail.observations) == 1
    obs = detail.observations[0].reported_file
    assert obs.duration_seconds is None
    assert obs.bitrate_kbps is None


def test_file_history_observations_include_media_fields_present(catalog_db: Path) -> None:
    """An observation's duration_seconds and bitrate_kbps are filled when present."""
    h = "d" * 32
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, h, 150)
        insert_observation(
            conn,
            h,
            "keroro_media.avi",
            size_bytes=150,
            source_count=3,
            duration_seconds=1320,
            bitrate_kbps=192,
        )
    detail = _history(catalog_db, h)
    assert detail is not None
    assert len(detail.observations) == 1
    obs = detail.observations[0].reported_file
    assert obs.duration_seconds == 1320
    assert obs.bitrate_kbps == 192


def _seed_retracted(db: Path) -> None:
    """Add a third file (c*32) that WAS matched (063A) then had that target retracted
    per-target: a ``(hash, 063A, tier="retracted")`` marker appended after the real decision
    (the new per-target retraction model, spec §6). Its latest 063A row is a retraction, so
    it must be treated as unmatched everywhere."""
    h = "c" * 32
    with sqlite3.connect(db) as conn:
        insert_file(conn, h, 300)
        insert_observation(
            conn,
            h,
            "keroro_063.avi",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=300,
            source_count=2,
        )
        insert_decision(conn, h, "063A", "download", rule_name="id_segment_exact")
        insert_decision(
            conn,
            h,
            "063A",
            "retracted",
            rule_name="",
            decided_at="2026-06-22T11:00:00.000000+00:00",
        )


def _seed_unmatched(db: Path) -> None:
    """Add a second file (b*32) with an observation but NO match decision."""
    with sqlite3.connect(db) as conn:
        insert_file(conn, "b" * 32, 200)
        insert_observation(
            conn,
            "b" * 32,
            "gallego_ep021.ogm",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=200,
        )


def test_list_files_matched_only_excludes_unmatched(catalog_db: Path) -> None:
    _seed(catalog_db)
    _seed_unmatched(catalog_db)
    rows = _entries(catalog_db, matched_only=True)
    hashes = {r.file.native_id for r in rows}
    assert hashes == {"a" * 32}  # only the matched file


def test_list_files_matched_only_excludes_retracted(catalog_db: Path) -> None:
    """A file whose latest decision is a retraction is NOT matched, even though its
    ``target_id`` column is non-NULL (the crawler's sentinel is an empty string, not NULL)."""
    _seed(catalog_db)
    _seed_retracted(catalog_db)
    rows = _entries(catalog_db, matched_only=True)
    hashes = {r.file.native_id for r in rows}
    assert hashes == {"a" * 32}  # the retracted file ("c"*32) is excluded


def test_list_files_lists_a_retracted_file_with_no_decision(catalog_db: Path) -> None:
    _seed_retracted(catalog_db)
    [row] = _entries(catalog_db)
    assert row.decisions == ()


def test_list_files_default_includes_unmatched(catalog_db: Path) -> None:
    _seed(catalog_db)
    _seed_unmatched(catalog_db)
    rows = _entries(catalog_db)
    hashes = {r.file.native_id for r in rows}
    assert hashes == {"a" * 32, "b" * 32}  # default matched_only=False → both


def test_list_files_shows_latest_observation(catalog_db: Path) -> None:
    """Same hash with two observations → list_files returns the most recent filename."""
    h = "c" * 32
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, h, 300)
        insert_observation(
            conn,
            h,
            "old_name.avi",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=300,
        )
        insert_observation(
            conn,
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
# Tests: count_files, /files summary (matched, total)
# ---------------------------------------------------------------------------


def test_count_files_no_filter_returns_matched_and_total(catalog_db: Path) -> None:
    _seed(catalog_db)  # 1 matched file
    _seed_unmatched(catalog_db)  # 1 unmatched file
    matched, total = _counts(catalog_db)
    assert (matched, total) == (1, 2)


def test_count_files_respects_query_filter(catalog_db: Path) -> None:
    _seed(catalog_db)  # filename keroro_062.avi (matched)
    _seed_unmatched(catalog_db)  # filename gallego_ep021.ogm (unmatched)
    matched, total = _counts(catalog_db, search_text="gallego")
    assert (matched, total) == (0, 1)  # only the unmatched file matches the query


def test_count_files_counts_retracted_as_unmatched(catalog_db: Path) -> None:
    """A retracted file counts toward ``total`` but not ``matched`` (the matched count is
    unchanged by its presence, even though its ``target_id`` column is non-NULL)."""
    _seed(catalog_db)  # 1 matched file
    _seed_retracted(catalog_db)  # 1 retracted (== unmatched) file
    matched, total = _counts(catalog_db)
    assert (matched, total) == (1, 2)


def test_count_files_empty_catalogue_matched_is_zero_not_none(catalog_db: Path) -> None:
    """Regression guard for the COUNT → SUM(CASE ...) rewrite: SUM over zero rows is NULL in
    SQL, unlike COUNT which is 0. An empty catalogue must still report ``matched == 0``."""
    matched, total = _counts(catalog_db)
    assert (matched, total) == (0, 0)


# ---------------------------------------------------------------------------
# Tests: target-scoped read excludes catalog-tier (catch-all pinned to 001A)
# ---------------------------------------------------------------------------


def _seed_catalog_tier_on_001a(db: Path) -> None:
    """A keroro_large catch-all file: its only decision is tier 'catalog' pinned to 001A."""
    with sqlite3.connect(db) as conn:
        insert_file(conn, "b" * 32, 50)
        insert_observation(
            conn,
            "b" * 32,
            "keroro manga.zip",
            observed_at="2026-07-01T10:00:00.000000+00:00",
            size_bytes=50,
        )
        insert_decision(
            conn,
            "b" * 32,
            "001A",
            "catalog",
            rule_name="keroro_large",
            decided_at="2026-07-01T10:00:01.000000+00:00",
        )


def test_target_scope_excludes_catalog_tier(catalog_db: Path) -> None:
    """A catalog-tier decision pinned to 001A must NOT surface under target='001A'."""
    _seed_catalog_tier_on_001a(catalog_db)
    rows = _entries(catalog_db, target_id="001A")
    assert rows == ()
    matched, _total = _counts(catalog_db, target_id="001A")
    assert matched == 0


def test_target_scope_keeps_non_catalog_tier(catalog_db: Path) -> None:
    """A non-catalog (download) decision on 062A is still returned under target='062A'."""
    _seed(catalog_db)  # existing helper: a 'download' decision on 062A
    rows = _entries(catalog_db, target_id="062A")
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Tests: sortable list_files via the fixed column allowlist + best_tier_rank
# ---------------------------------------------------------------------------


def _seed_sortable(db: Path) -> None:
    """Three single-decision files with distinct sort keys and one decision each at a distinct
    tier (download > notify > catalog), for the sort-order tests.

    hash 'a': beta.avi  size 300 sources  5 seen 2026-01-01 tier notify   (062A)
    hash 'b': alpha.avi size 100 sources 15 seen 2026-01-02 tier download (072A)
    hash 'c': gamma.avi size 200 sources 10 seen 2026-01-03 tier catalog  (keroro_large)

    Every sort key yields a distinct order, and ``last_seen`` (a < b < c) is deliberately
    orthogonal to BOTH ``size`` (a is largest) AND ``tier`` (b is strongest): so a sort column
    that silently swaps to ``observed_at`` cannot pass unnoticed on any key, including ``tier``.
    """
    rows = [
        ("a" * 32, "beta.avi", 300, 5, "2026-01-01T10:00:00.000000+00:00", "062A", "notify"),
        ("b" * 32, "alpha.avi", 100, 15, "2026-01-02T10:00:00.000000+00:00", "072A", "download"),
        ("c" * 32, "gamma.avi", 200, 10, "2026-01-03T10:00:00.000000+00:00", "001A", "catalog"),
    ]
    with sqlite3.connect(db) as conn:
        for h, name, size, sources, seen, tid, tier in rows:
            insert_file(conn, h, size)
            insert_observation(
                conn, h, name, observed_at=seen, size_bytes=size, source_count=sources
            )
            insert_decision(conn, h, tid, tier, decided_at="2026-01-04T10:00:00.000000+00:00")


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
def test_list_files_sort_orders(
    catalog_db: Path, sort: str, direction: str, expected: list[str]
) -> None:
    _seed_sortable(catalog_db)
    rows = _entries(catalog_db, sort=CatalogEntrySort(sort), direction=SortDirection(direction))
    assert _hashes(rows) == [c * 32 for c in expected]


def test_list_files_sort_tiebreak_is_file_id(catalog_db: Path) -> None:
    """Two files with the same sort key keep a deterministic order via the file_id tiebreak."""
    with sqlite3.connect(catalog_db) as conn:
        for h in ("a" * 32, "e" * 32):  # inserted a-first on purpose
            insert_file(conn, h)
            insert_observation(conn, h, "same.avi", observed_at="2026-01-01T10:00:00.000000+00:00")
    rows = _entries(catalog_db, sort=CatalogEntrySort.SIZE, direction=SortDirection.ASC)
    assert _hashes(rows) == ["e" * 32, "a" * 32]  # e's file_id sorts first


def test_tier_rank_case_matches_tier_rank() -> None:
    """The generated CASE maps every tier to its TIER_RANK integer (single-source guard: red if
    the CASE and the dict diverge)."""
    sql = _tier_rank_case("ld.tier")
    for tier, rank in TIER_RANK.items():
        assert f"WHEN '{tier}' THEN {rank}" in sql


def test_every_sort_has_its_column() -> None:
    assert set(SORT_COLUMNS) == set(CatalogEntrySort)


# ---------------------------------------------------------------------------
# Tests: tier_counts, the tier facet's live counts (spec §3.3)
# ---------------------------------------------------------------------------


def _seed_mixed_tier_file(db: Path) -> None:
    """One file with TWO current decisions in DIFFERENT tiers (download + notify): it must count
    under both facets."""
    h = "d" * 32
    with sqlite3.connect(db) as conn:
        insert_file(conn, h)
        insert_observation(conn, h, "mixed.avi", observed_at="2026-01-01T10:00:00.000000+00:00")
        for tid, tier in (("062A", "download"), ("062B", "notify")):
            insert_decision(conn, h, tid, tier, decided_at="2026-01-02T10:00:00.000000+00:00")


def test_tier_counts_groups_by_tier(catalog_db: Path) -> None:
    _seed_sortable(catalog_db)  # one file per tier
    counts = _tier_counts(catalog_db)
    assert counts == {"download": 1, "notify": 1, "catalog": 1}


def test_tier_counts_empty_catalogue_is_empty(catalog_db: Path) -> None:
    counts = _tier_counts(catalog_db)
    assert counts == {}


def test_tier_counts_multi_tier_file_counts_in_both(catalog_db: Path) -> None:
    _seed_mixed_tier_file(catalog_db)
    counts = _tier_counts(catalog_db)
    assert counts == {"download": 1, "notify": 1}


def test_tier_counts_respects_query_filter(catalog_db: Path) -> None:
    """The facet honours the OTHER filters (here ``query``): only alpha.avi (download) matches."""
    _seed_sortable(catalog_db)
    counts = _tier_counts(catalog_db, search_text="alpha")
    assert counts == {"download": 1}


# ---------------------------------------------------------------------------
# Files with no observation / tied observations
# ---------------------------------------------------------------------------


def _seed_file_without_observation(db: Path) -> str:
    """A file with NO observation at all (a file row is written before its first observation is
    recorded). Returns its hash."""
    h = "d" * 32
    with sqlite3.connect(db) as conn:
        insert_file(conn, h, 42)
    return h


def test_list_files_lists_file_with_no_observation(catalog_db: Path) -> None:
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


def test_count_files_counts_file_with_no_observation(catalog_db: Path) -> None:
    """It counts in ``total`` (it is a catalogued file) but not in ``matched`` (no decision)."""
    _seed_file_without_observation(catalog_db)
    matched, total = _counts(catalog_db)
    assert (matched, total) == (0, 1)


def test_list_files_query_filter_excludes_file_with_no_observation(catalog_db: Path) -> None:
    """No observation means no filename to match: ``NULL LIKE ?`` is NULL, so the row drops."""
    _seed_file_without_observation(catalog_db)
    rows = _entries(catalog_db, search_text="keroro")
    assert rows == ()


def test_list_files_observation_tie_break_on_the_newest_variant(catalog_db: Path) -> None:
    """Two observations at the SAME ``observed_at``: the higher ``variant_id`` wins (D4)."""
    h = "a" * 32
    with sqlite3.connect(catalog_db) as conn:
        insert_file(conn, h)
        for name in ("first.avi", "second.avi"):  # same instant, ascending variant ids
            insert_observation(conn, h, name, observed_at="2026-07-03T10:00:00.000000+00:00")
    rows = _entries(catalog_db)
    assert _latest_filename(rows[0]) == "second.avi"


def test_file_history_of_a_file_never_seen_has_no_observation(catalog_db: Path) -> None:
    h = _seed_file_without_observation(catalog_db)
    detail = _history(catalog_db, h)
    assert detail is not None
    assert (detail.observations, detail.latest_observation, detail.known_filenames) == (
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
        ("list_files", _SQL_LIST_FILES_BASE + "ORDER BY obs.observed_at DESC LIMIT 50"),
        ("count_files", _SQL_COUNT_FILES_BASE + _JOIN_LATEST_OBSERVATION + _JOIN_DECISIONS),
        ("tier_counts", _SQL_TIER_COUNTS_BASE + _JOIN_LATEST_OBSERVATION + "GROUP BY ld.tier"),
    ],
    ids=["latest_observation alone", "list_files", "count_files", "tier_counts"],
)
def test_latest_obs_seeks_per_file_instead_of_scanning_observations(
    catalog_db: Path, label: str, sql: str
) -> None:
    """Every /files query reading the latest observation SEEKS each variant's observations by
    primary key, never walks ``observations`` (11.6M rows on the node). Asserts the PLAN, not a
    duration, so it stays deterministic; each real query is checked, not the CTE alone."""
    plan = [str(row[3]) for row in open_reader(catalog_db).execute("EXPLAIN QUERY PLAN " + sql)]

    assert any(re.match(r"SEARCH o\w* USING PRIMARY KEY \(variant_id=\?", step) for step in plan), (
        f"{label} does not seek observations by key: {plan}"
    )
    assert not any(step.startswith("SCAN o") for step in plan), f"{label} scans: {plan}"


_COUNTERS: dict[str, Callable[[SqliteCatalogFileReader, str | None], object]] = {
    "count_files": lambda reader, search_text: reader.read_matched_and_total_file_counts(
        target_id=None, tier=None, search_text=search_text
    ),
    "tier_counts": lambda reader, search_text: reader.read_file_count_by_tier(
        target_id=None, search_text=search_text
    ),
}


@pytest.mark.parametrize("counter", sorted(_COUNTERS))
@pytest.mark.parametrize("query", [None, "keroro"])
def test_counters_read_observations_only_for_a_name_filter(
    catalog_db: Path, counter: str, query: str | None
) -> None:
    """The default /files page counts without a per-file latest observation (D18)."""
    reader_provider = ReaderProvider(catalog_db)
    tables: set[str] = set()

    def record(action: int, table: str | None, *_: str | None) -> int:
        if action == sqlite3.SQLITE_READ and table is not None:
            tables.add(table)
        return sqlite3.SQLITE_OK

    reader_provider.connection().set_authorizer(record)
    _COUNTERS[counter](SqliteCatalogFileReader(reader_provider), query)
    assert ("observations" in tables) is (query is not None)
