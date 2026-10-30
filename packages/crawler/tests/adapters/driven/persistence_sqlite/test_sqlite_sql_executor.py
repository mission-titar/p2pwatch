"""TDD tests for ``SqliteSqlExecutor``, the read-only SQL console's execution adapter (spec §11).

The tests seed a real ``catalog.db`` via the writer (``open_catalog``) so ``open_reader`` has a
real ``mode=ro`` file to open.
"""

from datetime import timedelta
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.sqlite_sql_executor import SqliteSqlExecutor
from p2pwatch.domain.console_query import QueryAnswer, QueryFailure
from p2pwatch.domain.file_key import FileKey, Network
from tests.fakes.adapters.driven.fake_ticking_monotonic_clock import FakeTickingMonotonicClock
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.support.adapters.driven.persistence_sqlite.sqlite_database_opener import (
    open_catalog,
    open_reader,
)
from tests.support.catalog_rows import insert_file

_HASH_A = "a" * 32
_TIME_LIMIT = timedelta(seconds=5)
_BUDGET_CHECK_INSTRUCTIONS = 1000
# A few hundredths of a second of real time, past a 5 s budget on a FakeTickingMonotonicClock.
_PAST_BUDGET_SQL = (
    "WITH RECURSIVE r(i) AS (SELECT 0 UNION ALL SELECT i + 1 FROM r WHERE i < 100000)"
    " SELECT count(*) FROM r"
)


def _seed_catalog(path: Path) -> None:
    """Create + seed a real catalog.db via the writer."""
    writer = open_catalog(path)
    try:
        insert_file(writer, native_id=_HASH_A, size_bytes=10)
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# SqliteSqlExecutor · the execution adapter (spec §11)
# ---------------------------------------------------------------------------


def test_select_returns_columns_and_rows(tmp_path: Path) -> None:
    """A SELECT returns the column names and the stringified rows, no error, not truncated, timed
    on the monotonic clock: one tick between its start and its end."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTickingMonotonicClock(FakeTime()),
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "SELECT native_id, size_bytes FROM files",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert query_answer == QueryAnswer(
        columns=("native_id", "size_bytes"),
        rows=((_HASH_A, "10"),),
        elapsed=timedelta(seconds=1),
        truncated=False,
    )


def test_a_column_name_repeated_keeps_both_columns_in_order(tmp_path: Path) -> None:
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTickingMonotonicClock(FakeTime()),
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute("SELECT 1 AS a, 2 AS a", row_cap=1000, time_limit=_TIME_LIMIT)
    assert query_answer == QueryAnswer(
        columns=("a", "a"), rows=(("1", "2"),), elapsed=timedelta(seconds=1), truncated=False
    )


def test_renders_none_cell_as_null_literal(tmp_path: Path) -> None:
    """A NULL cell is rendered as the literal string ``NULL`` (not an empty cell)."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "SELECT NULL AS missing FROM files",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert isinstance(query_answer, QueryAnswer)
    assert query_answer.rows == (("NULL",),)


def test_renders_a_blob_cell_as_lowercase_hex(tmp_path: Path) -> None:
    """A ``file_id`` reads as the hex its detail page's URL takes, not as a Python repr."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "SELECT file_id FROM files",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert isinstance(query_answer, QueryAnswer)
    assert query_answer.rows == ((FileKey(network=Network.ED2K, native_id=_HASH_A).file_id.hex(),),)


def test_write_is_rejected_read_only(tmp_path: Path) -> None:
    """A write statement is structurally impossible (mode=ro + query_only) -> read-only error."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "INSERT INTO files (native_id, size_bytes) VALUES ('b', 1)",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert query_answer == QueryFailure(
        message="The database is read-only. Only read queries (SELECT) are allowed."
    )


def test_multi_statement_is_rejected(tmp_path: Path) -> None:
    """Two statements in one input -> single-statement error (sqlite3.ProgrammingError)."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "SELECT 1; SELECT 2",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert query_answer == QueryFailure(message="Only a single SQL statement is allowed per query.")


def test_row_cap_truncates_and_flags(tmp_path: Path) -> None:
    """More rows than the cap: keep the first ``row_cap`` and flag truncation."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r WHERE x < 5)"
        " SELECT x FROM r",
        row_cap=2,
        time_limit=_TIME_LIMIT,
    )
    assert isinstance(query_answer, QueryAnswer)
    assert query_answer.truncated is True
    assert query_answer.rows == (("1",), ("2",))


def test_runaway_is_aborted_by_timeout(tmp_path: Path) -> None:
    """A query past its budget of monotonic time is aborted, and the error is the timeout message,
    distinct from a generic SQL error."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTickingMonotonicClock(FakeTime()),
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        _PAST_BUDGET_SQL,
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert query_answer == QueryFailure(
        message="Query aborted: it exceeded the 5 second time limit."
    )


def test_the_budget_is_checked_only_at_its_step_of_instructions(tmp_path: Path) -> None:
    """A step longer than the whole query never checks the budget, so nothing aborts it."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTickingMonotonicClock(FakeTime()),
        budget_check_instructions=10**9,
    ).execute(_PAST_BUDGET_SQL, row_cap=1000, time_limit=_TIME_LIMIT)
    assert query_answer == QueryAnswer(
        columns=("count(*)",), rows=(("100001",),), elapsed=timedelta(seconds=1), truncated=False
    )


def test_malformed_sql_yields_error_not_exception(tmp_path: Path) -> None:
    """A syntax error is absorbed into an error result (not raised) - the read-only console
    boundary absorbs arbitrary operator SQL."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "SELECT FROM",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert query_answer == QueryFailure(message='SQL error: near "FROM": syntax error')


def test_other_sqlite_error_is_absorbed(tmp_path: Path) -> None:
    """A non-Operational, non-Programming sqlite3.Error (here a DataError: blob too big) is
    caught by the console catch-all and absorbed into an error result."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "SELECT length(zeroblob(1000000000000))",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert query_answer == QueryFailure(message="SQL error: string or blob too big")


def test_statement_without_result_columns_is_safe(tmp_path: Path) -> None:
    """A read-only statement that returns no result set (cursor.description is None, e.g. a
    comment-only input) yields empty columns/rows, never a crash."""
    path = tmp_path / "catalog.db"
    _seed_catalog(path)
    query_answer = SqliteSqlExecutor(
        path,
        open_reader=open_reader,
        monotonic_clock=FakeTime().monotonic,
        budget_check_instructions=_BUDGET_CHECK_INSTRUCTIONS,
    ).execute(
        "-- just a comment",
        row_cap=1000,
        time_limit=_TIME_LIMIT,
    )
    assert isinstance(query_answer, QueryAnswer)
    assert (query_answer.columns, query_answer.rows) == ((), ())
