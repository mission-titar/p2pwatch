"""``RunConsoleQuery``: the operator's SQL on the database they chose, capped and time-limited."""

from datetime import timedelta

from p2pwatch.application.ports.driving.console_query_runner import ConsoleQueryRun
from p2pwatch.application.use_cases.run_console_query import RunConsoleQuery
from p2pwatch.domain.console_query import ConsoleDatabase, QueryAnswer
from tests.fakes.adapters.driven.fake_sql_executor import ExecuteCall, FakeSqlExecutor

_ANSWER = QueryAnswer(("x",), (("1",),), timedelta(milliseconds=3), truncated=False)


def test_a_query_runs_on_the_chosen_database_only_capped_at_1000_rows_and_5_seconds() -> None:
    catalog, local = FakeSqlExecutor(_ANSWER), FakeSqlExecutor(_ANSWER)
    run_console_query = RunConsoleQuery(
        {ConsoleDatabase.CATALOG: catalog, ConsoleDatabase.LOCAL: local}
    ).run_console_query

    outcome = run_console_query(ConsoleDatabase.LOCAL, "SELECT 1")

    assert local.calls == [ExecuteCall("SELECT 1", 1000, timedelta(seconds=5))]
    assert catalog.calls == []
    assert outcome == ConsoleQueryRun(_ANSWER, row_cap=1000)
