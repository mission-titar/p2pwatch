"""TDD tests for the read-only SQL console's ``run_query`` execution adapter (spec §11).

The tests seed a real ``catalog.db`` via the writer (``open_catalog``) so ``open_reader`` has a
real ``mode=ro`` file to open, exactly like the ``test_reader.py`` persistence tests.
"""

from pathlib import Path

from p2pwatch.adapters.persistence_sqlite.connection import open_catalog
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.webui.adapters.sql_console import ConsoleOutcome, run_query
from p2pwatch_testing.application.fakes import FakeTime, TickingMonotonicClock
from p2pwatch_testing.catalog_rows import insert_file

_HASH_A = "a" * 32
# A few hundredths of a second of real time, past a 5 s budget on a TickingMonotonicClock.
_PAST_BUDGET_SQL = (
    "WITH RECURSIVE r(i) AS (SELECT 0 UNION ALL SELECT i + 1 FROM r WHERE i < 100000)"
    " SELECT count(*) FROM r"
)


def _seed_catalog(path: Path) -> None:
    """Create + seed a real catalog.db via the writer."""
    writer = open_catalog(path)
    try:
        insert_file(writer, _HASH_A, 10)
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# run_query · the execution adapter (spec §11)
# ---------------------------------------------------------------------------


def test_run_query_select_returns_columns_and_rows(tmp_path: Path) -> None:
    """A SELECT returns the column names and the stringified rows, no error, not truncated, timed
    on the monotonic clock: one tick between its start and its end."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="SELECT native_id, size_bytes FROM files",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=TickingMonotonicClock(FakeTime()),
    )
    assert outcome.error is None
    assert outcome.columns == ("native_id", "size_bytes")
    assert outcome.rows == ((_HASH_A, "10"),)
    assert outcome.row_count == 1
    assert outcome.truncated is False
    assert outcome.elapsed_ms == 1000


def test_run_query_renders_none_cell_as_null_literal(tmp_path: Path) -> None:
    """A NULL cell is rendered as the literal string ``NULL`` (not an empty cell)."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="SELECT NULL AS missing FROM files",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.error is None
    assert outcome.rows == (("NULL",),)


def test_run_query_renders_a_blob_cell_as_lowercase_hex(tmp_path: Path) -> None:
    """A ``file_id`` reads as the hex its detail page's URL takes, not as a Python repr."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="SELECT file_id FROM files",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.rows == ((FileKey(Network.ED2K, _HASH_A).file_id.hex(),),)


def test_run_query_write_is_rejected_read_only(tmp_path: Path) -> None:
    """A write statement is structurally impossible (mode=ro + query_only) -> read-only error."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="INSERT INTO files (native_id, size_bytes) VALUES ('b', 1)",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.error is not None
    assert "read-only" in outcome.error
    assert outcome.rows == ()


def test_run_query_multi_statement_is_rejected(tmp_path: Path) -> None:
    """Two statements in one input -> single-statement error (sqlite3.ProgrammingError)."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="SELECT 1; SELECT 2",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.error is not None
    assert "single" in outcome.error.lower()


def test_run_query_row_cap_truncates_and_flags(tmp_path: Path) -> None:
    """More rows than the cap: keep the first ``row_cap`` and flag truncation."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 5)"
        " SELECT x FROM r",
        row_cap=2,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.error is None
    assert outcome.truncated is True
    assert outcome.row_count == 2
    assert outcome.rows == (("1",), ("2",))


def test_run_query_runaway_is_aborted_by_timeout(tmp_path: Path) -> None:
    """A query past its budget of monotonic time is aborted, and the error is the timeout message,
    distinct from a generic SQL error."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql=_PAST_BUDGET_SQL,
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=TickingMonotonicClock(FakeTime()),
    )
    assert outcome.error is not None
    assert "time limit" in outcome.error
    assert "SQL error" not in outcome.error


def test_run_query_malformed_sql_yields_error_not_exception(tmp_path: Path) -> None:
    """A syntax error is absorbed into an error result (not raised) - the read-only console
    boundary absorbs arbitrary operator SQL."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="SELECT FROM",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.error is not None
    assert "syntax" in outcome.error.lower()


def test_run_query_other_sqlite_error_is_absorbed(tmp_path: Path) -> None:
    """A non-Operational, non-Programming sqlite3.Error (here a DataError: blob too big) is
    caught by the console catch-all and absorbed into an error result."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="SELECT length(zeroblob(1000000000000))",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.error is not None
    assert "too big" in outcome.error


def test_run_query_statement_without_result_columns_is_safe(tmp_path: Path) -> None:
    """A read-only statement that returns no result set (cursor.description is None, e.g. a
    comment-only input) yields empty columns/rows, never a crash."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    outcome = run_query(
        db_path=path,
        sql="-- just a comment",
        row_cap=1000,
        timeout_seconds=5.0,
        monotonic_clock=FakeTime().monotonic,
    )
    assert outcome.error is None
    assert outcome.columns == ()
    assert outcome.rows == ()
    assert outcome.row_count == 0


def test_console_outcome_defaults_are_empty() -> None:
    """An error outcome only sets ``error``; the rest default to empty/zero."""
    outcome = ConsoleOutcome(error="boom")
    assert outcome.columns == ()
    assert outcome.rows == ()
    assert outcome.row_count == 0
    assert outcome.truncated is False
