from dataclasses import dataclass

from p2pwatch.application.ports.driving.console_query_runner import (
    ConsoleQueryRun,
    ConsoleQueryRunner,
)
from p2pwatch.domain.console_query import ConsoleDatabase


@dataclass(frozen=True)
class RunConsoleQueryCall:
    """The arguments of one ``run_console_query`` call."""

    database: ConsoleDatabase
    sql: str


class FakeConsoleQueryRunner(ConsoleQueryRunner):
    """Answers any query with the run it is given, and keeps each call's arguments."""

    def __init__(self, console_query_run: ConsoleQueryRun) -> None:
        self._console_query_run = console_query_run
        self.calls: list[RunConsoleQueryCall] = []

    def run_console_query(self, database: ConsoleDatabase, sql: str) -> ConsoleQueryRun:
        self.calls.append(RunConsoleQueryCall(database, sql))
        return self._console_query_run
