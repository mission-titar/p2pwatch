"""Read-only SQL console execution adapter (monolith-consolidation spec §11).

This is an ADAPTER (an I/O boundary), so unlike the pure domain it MAY use ``sqlite3`` directly;
it measures time on the ``MonotonicClock`` it is given. It runs an operator-supplied SQL string
against a FRESH read-only connection and returns a ``QueryAnswer`` (rows + timing) or a
``QueryFailure``.

Why a fresh, dedicated connection per query (not the shared ``ThreadReadConnections``): the console
sets a PER-QUERY progress handler (the monotonic budget's abort) and a runaway query is aborted
mid-flight; isolating that on its own connection keeps it from disturbing the reused page-serving
readers. The connection is always closed in a ``finally``.

Three guardrails make this structurally safe against a hostile / clumsy operator (writes are
already impossible, so these are the real risks, spec §11/§12):

- **Read-only** is doubly enforced by ``open_reader`` (OS-level ``mode=ro`` PLUS
  ``PRAGMA query_only=ON``): a write raises ``sqlite3.OperationalError`` ("attempt to write a
  readonly database"), mapped to a clear read-only error.
- **Single statement**: ``Connection.execute`` runs exactly one statement and rejects a second
  ("SELECT 1; SELECT 2") with ``sqlite3.ProgrammingError`` ("You can only execute one statement at
  a time"), mapped to a single-statement error.
- **Monotonic timeout**: a ``set_progress_handler`` callback fires every
  ``budget_check_instructions`` VM steps and returns non-zero once the time elapsed on the
  monotonic clock exceeds the budget, which aborts the query with ``sqlite3.OperationalError``
  ("interrupted"). A mutable flag records the abort so the handler can be distinguished from an
  unrelated ``OperationalError`` (e.g. a syntax error).
- **Row cap**: at most ``row_cap`` rows are returned; one extra row is fetched to detect (and flag)
  truncation.

**Boundary discipline (E-D13).** Elsewhere in the codebase, in-process 100%-tested code crashes
loudly on failure. This adapter is the deliberate exception: a console query is *arbitrary operator
input*, so a malformed query, a write attempt, a multi-statement input, a runaway query, or any
other ``sqlite3.Error`` is EXPECTED user error and is absorbed into a ``QueryFailure`` instead
of crashing the request handler. This is a documented boundary absorption, NOT a silent swallow of
an internal bug (which would still surface: a bug in this module's own logic is not a
``sqlite3.Error`` and would propagate).
"""

import sqlite3
from datetime import timedelta
from pathlib import Path

from p2pwatch.adapters.driven.persistence_sqlite.thread_read_connections import open_reader
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.ports.driven.sql_executor import SqlExecutor
from p2pwatch.domain.console_query import QueryAnswer, QueryFailure


def _stringify(cell: object) -> str:
    """Render a cell for display: ``None`` becomes the literal ``NULL`` (an empty cell would be
    ambiguous), a BLOB its lowercase hex, everything else its ``str``."""
    if cell is None:
        return "NULL"
    return cell.hex() if isinstance(cell, bytes) else str(cell)


class SqliteSqlExecutor(SqlExecutor):
    """Runs the console's SQL on the SQLite database at ``db_path``, its budget measured on
    ``monotonic_clock`` every ``budget_check_instructions`` VM steps."""

    def __init__(
        self, db_path: Path, monotonic_clock: MonotonicClock, *, budget_check_instructions: int
    ) -> None:
        self._db_path = db_path
        self._monotonic_clock = monotonic_clock
        self._budget_check_instructions = budget_check_instructions

    def execute(
        self, sql: str, *, row_cap: int, time_limit: timedelta
    ) -> QueryAnswer | QueryFailure:
        return _run_query(
            db_path=self._db_path,
            sql=sql,
            row_cap=row_cap,
            budget=time_limit,
            monotonic_clock=self._monotonic_clock,
            budget_check_instructions=self._budget_check_instructions,
        )


def _run_query(
    *,
    db_path: Path,
    sql: str,
    row_cap: int,
    budget: timedelta,
    monotonic_clock: MonotonicClock,
    budget_check_instructions: int,
) -> QueryAnswer | QueryFailure:
    """Run ``sql`` read-only against ``db_path``.

    See the module docstring for the read-only / single-statement / timeout / row-cap guardrails
    and the deliberate absorption of ``sqlite3.Error`` into a ``QueryFailure``.
    """
    connection = open_reader(db_path)
    try:
        start = monotonic_clock.now()
        aborted = [False]

        def _progress() -> int:
            # Abort (non-zero) once the monotonic budget is exceeded; record it so the
            # OperationalError handler can tell a timeout abort from a genuine SQL error.
            if monotonic_clock.now() - start > budget:
                aborted[0] = True
                return 1
            return 0

        connection.set_progress_handler(_progress, budget_check_instructions)
        try:
            cursor = connection.execute(sql)
            fetched = cursor.fetchmany(row_cap + 1)
            elapsed = monotonic_clock.now() - start
            truncated = len(fetched) > row_cap
            kept = fetched[:row_cap]
            description = cursor.description
            columns = tuple(col[0] for col in description) if description is not None else ()
            rows = tuple(tuple(_stringify(cell) for cell in row) for row in kept)
            return QueryAnswer(columns, rows, elapsed, truncated)
        except sqlite3.OperationalError as exc:
            if aborted[0]:
                seconds = budget.total_seconds()
                return QueryFailure(
                    f"Query aborted: it exceeded the {seconds:g} second time limit."
                )
            if "readonly" in str(exc):
                return QueryFailure(
                    "The database is read-only. Only read queries (SELECT) are allowed."
                )
            return QueryFailure(f"SQL error: {exc}")
        except sqlite3.ProgrammingError:
            # In this console (no parameter binding) the sole realistic ProgrammingError is the
            # multi-statement guard ("You can only execute one statement at a time").
            return QueryFailure("Only a single SQL statement is allowed per query.")
        except sqlite3.Error as exc:
            # Catch-all for any other sqlite3 failure (e.g. a DataError: blob too big). Absorbed
            # into a failure, per the boundary discipline in the module docstring.
            return QueryFailure(f"SQL error: {exc}")
    finally:
        connection.close()
