"""``RunConsoleQuery``: the operator's SQL on the database they chose, capped and time-limited."""

from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.application.ports.driven.sql_executor import SqlExecutor
from p2pwatch.application.ports.driving.console_query_runner import ConsoleQueryOutcome
from p2pwatch.application.use_cases.run_console_query import RunConsoleQuery
from p2pwatch.domain.console_query import ConsoleDatabase, QueryAnswer, QueryFailure


@dataclass(frozen=True)
class ExecuteCall:
    sql: str
    row_cap: int
    time_limit: timedelta


class FakeSqlExecutor(SqlExecutor):
    """Answers every statement as it is given, and keeps each call's arguments."""

    def __init__(self, query_answer: QueryAnswer | QueryFailure) -> None:
        self._query_answer = query_answer
        self.calls: list[ExecuteCall] = []

    def execute(
        self, sql: str, *, row_cap: int, time_limit: timedelta
    ) -> QueryAnswer | QueryFailure:
        self.calls.append(ExecuteCall(sql, row_cap, time_limit))
        return self._query_answer


_ANSWER = QueryAnswer(("x",), (("1",),), timedelta(milliseconds=3), truncated=False)


def test_a_query_runs_on_the_chosen_database_only_capped_at_1000_rows_and_5_seconds() -> None:
    catalog, local = FakeSqlExecutor(_ANSWER), FakeSqlExecutor(_ANSWER)
    run_console_query = RunConsoleQuery(
        {ConsoleDatabase.CATALOG: catalog, ConsoleDatabase.LOCAL: local}
    ).run_console_query

    outcome = run_console_query(ConsoleDatabase.LOCAL, "SELECT 1")

    assert local.calls == [ExecuteCall("SELECT 1", 1000, timedelta(seconds=5))]
    assert catalog.calls == []
    assert outcome == ConsoleQueryOutcome(_ANSWER, row_cap=1000)
