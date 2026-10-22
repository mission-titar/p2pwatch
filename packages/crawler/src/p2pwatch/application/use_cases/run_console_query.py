"""Runs the operator's SQL on one of the node's databases, row-capped and time-limited."""

from collections.abc import Mapping
from datetime import timedelta

from p2pwatch.application.ports.driven.sql_executor import SqlExecutor
from p2pwatch.application.ports.driving.console_query_runner import (
    ConsoleQueryRun,
    ConsoleQueryRunner,
)
from p2pwatch.domain.console_query import ConsoleDatabase

_ROW_CAP = 1000
_TIME_LIMIT = timedelta(seconds=5)


class RunConsoleQuery(ConsoleQueryRunner):
    def __init__(self, sql_executor_by_database: Mapping[ConsoleDatabase, SqlExecutor]) -> None:
        self._sql_executor_by_database = sql_executor_by_database

    def run_console_query(self, database: ConsoleDatabase, sql: str) -> ConsoleQueryRun:
        sql_executor = self._sql_executor_by_database[database]
        query_answer = sql_executor.execute(sql, row_cap=_ROW_CAP, time_limit=_TIME_LIMIT)
        return ConsoleQueryRun(query_answer, row_cap=_ROW_CAP)
