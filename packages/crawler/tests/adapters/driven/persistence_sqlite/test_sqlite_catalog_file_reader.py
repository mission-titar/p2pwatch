"""TDD tests for the catalog's file reader: filtered explorer, file history (spec W-D6 / §6)."""

import re
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
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
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_observation_store import (
    SqliteObservationStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import (
    ThreadReadConnections,
)
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_history import FileHistory
from tests.contracts.application.ports.driven.catalog_file_reader_contract import (
    CatalogFileReaderContract,
)
from tests.support.adapters.driven.persistence_sqlite.named_row import rows
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_reader,
)
from tests.support.catalog_rows import file_id, insert_file, insert_observation

# Selects the CTE under test on its own: SQLite drops the CTEs a query does not reference, so
# the resulting plan is exactly how ``latest_observation`` is resolved.
LATEST_OBSERVATION_PROBE = (
    "SELECT file_id, filename, source_count, observed_at_micros FROM latest_observation"
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_YEAR_3000 = datetime(3000, 1, 1, tzinfo=UTC)  # after every instant a test writes
_LIMIT = 50


@pytest.fixture
def connection(catalog_db: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(catalog_db)
    yield catalog
    catalog.close()


@pytest.fixture
def thread_read_connections(catalog_db: Path) -> Iterator[ThreadReadConnections]:
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        yield thread_read_connections


class TestSqliteCatalogFileReader(CatalogFileReaderContract):
    @pytest.fixture
    def observation_writer(self, connection: sqlite3.Connection) -> SqliteObservationStore:
        return SqliteObservationStore(connection)

    @pytest.fixture
    def decision_writer(self, connection: sqlite3.Connection) -> SqliteDecisionStore:
        return SqliteDecisionStore(connection)

    @pytest.fixture
    def reader(self, thread_read_connections: ThreadReadConnections) -> SqliteCatalogFileReader:
        return SqliteCatalogFileReader(thread_read_connections)


def _entries(
    catalog_db: Path,
    *,
    search_text: str | None = None,
    sort: CatalogEntrySort = CatalogEntrySort.LATEST_SEEN,
    direction: SortDirection = SortDirection.DESC,
) -> tuple[CatalogEntry, ...]:
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        return SqliteCatalogFileReader(thread_read_connections).read_catalog_entries(
            target_id=None,
            tier=None,
            search_text=search_text,
            matched_only=False,
            sort=sort,
            direction=direction,
            limit=_LIMIT,
            offset=0,
        )


def _counts(catalog_db: Path) -> tuple[int, int]:
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        return SqliteCatalogFileReader(thread_read_connections).read_matched_and_total_file_counts(
            target_id=None, tier=None, search_text=None
        )


def _latest_filename(catalog_entry: CatalogEntry) -> str | None:
    observation = catalog_entry.latest_observation
    return None if observation is None else observation.reported_file.filename


# ---------------------------------------------------------------------------
# Tests: sortable read_catalog_entries via the fixed column allowlist + best_tier_rank
# ---------------------------------------------------------------------------


def test_tier_rank_case_matches_tier_rank() -> None:
    """The generated CASE maps every tier to its ``DecisionTier.rank``."""
    sql = _tier_rank_case("ld.tier")
    for tier in DecisionTier:
        assert f"WHEN '{tier}' THEN {tier.rank}" in sql


def test_every_sort_has_its_column() -> None:
    assert set(SORT_COLUMNS) == set(CatalogEntrySort)


# ---------------------------------------------------------------------------
# Files with no observation / tied observations
# ---------------------------------------------------------------------------


def _seed_unmatched(db: Path) -> None:
    """Add a file (b*32) with an observation but NO match decision."""
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, native_id="b" * 32, size_bytes=200)
        insert_observation(
            connection,
            native_id="b" * 32,
            filename="gallego_ep021.ogm",
            observed_at="2026-06-22T09:00:00.000000+00:00",
            size_bytes=200,
        )


def _seed_file_without_observation(db: Path) -> str:
    """A file with NO observation at all (a file row is written before its first observation is
    recorded). Returns its hash."""
    h = "d" * 32
    with closing(sqlite3.connect(db)) as connection, connection:
        insert_file(connection, native_id=h, size_bytes=42)
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


@pytest.mark.parametrize(
    "sort", [CatalogEntrySort.NAME, CatalogEntrySort.SOURCES, CatalogEntrySort.LATEST_SEEN], ids=str
)
def test_read_catalog_entries_sorts_a_file_never_seen_first_ascending_last_descending(
    *, catalog_db: Path, sort: CatalogEntrySort
) -> None:
    never_seen = _seed_file_without_observation(catalog_db)
    _seed_unmatched(catalog_db)
    ascending, descending = (
        _entries(catalog_db, sort=sort, direction=direction)
        for direction in (SortDirection.ASC, SortDirection.DESC)
    )
    assert (ascending[0].file.native_id, descending[-1].file.native_id) == (never_seen, never_seen)


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
    """No observation means no filename to match: its fold is NULL, so the row drops."""
    _seed_file_without_observation(catalog_db)
    rows = _entries(catalog_db, search_text="keroro")
    assert rows == ()


def test_read_catalog_entries_observation_tie_break_on_the_newest_variant(catalog_db: Path) -> None:
    """Two observations at the SAME ``observed_at``: the higher ``variant_id`` wins (D4)."""
    h = "a" * 32
    with closing(sqlite3.connect(catalog_db)) as connection, connection:
        insert_file(connection, native_id=h)
        for name in ("first.avi", "second.avi"):  # same instant, ascending variant ids
            insert_observation(
                connection,
                native_id=h,
                filename=name,
                observed_at="2026-07-03T10:00:00.000000+00:00",
            )
    rows = _entries(catalog_db)
    assert _latest_filename(rows[0]) == "second.avi"


def _history(catalog_db: Path, *, native_id: str) -> FileHistory | None:
    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        reader = SqliteCatalogFileReader(thread_read_connections)
        return reader.read_file_history(file_id(native_id), since=_EPOCH, until=_YEAR_3000)


def test_file_history_of_a_file_never_seen_has_no_observation(catalog_db: Path) -> None:
    h = _seed_file_without_observation(catalog_db)
    file_history = _history(catalog_db, native_id=h)
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
    *, catalog_db: Path, label: str, sql: str
) -> None:
    """Every /files query reading the latest observation SEEKS each variant's observations by
    primary key, never walks ``observations`` (11.6M rows on the node). Asserts the PLAN, not a
    duration, so it stays deterministic; each real query is checked, not the CTE alone."""
    with closing(open_reader(catalog_db)) as reader:
        plan = [str(step["detail"]) for step in rows(reader, sql="EXPLAIN QUERY PLAN " + sql)]

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
    *, catalog_db: Path, counter: str, search_text: str | None
) -> None:
    """The default /files page counts without a per-file latest observation (D18)."""
    tables: set[str] = set()

    def record(action: int, table: str | None, *_: str | None) -> int:  # noqa: PLR0917
        if action == sqlite3.SQLITE_READ and table is not None:
            tables.add(table)
        return sqlite3.SQLITE_OK

    with ThreadReadConnections(catalog_db, open_reader=open_reader) as thread_read_connections:
        thread_read_connections.connection().set_authorizer(record)
        _COUNTERS[counter](
            SqliteCatalogFileReader(thread_read_connections), search_text=search_text
        )
    assert ("observations" in tables) is (search_text is not None)
