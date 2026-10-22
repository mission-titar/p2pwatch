from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.application.ports.driven.sql_executor import SqlExecutor
from p2pwatch.domain.console_query import QueryAnswer, QueryFailure


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
