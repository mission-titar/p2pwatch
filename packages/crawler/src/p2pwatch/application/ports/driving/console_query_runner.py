"""``ConsoleQueryRunner``: runs the operator's SQL, for the console."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from p2pwatch.domain.console_query import ConsoleDatabase, QueryAnswer, QueryFailure


@dataclass(frozen=True)
class ConsoleQueryRun:
    query_answer: QueryAnswer | QueryFailure
    row_cap: int  # the most rows an answer keeps


class ConsoleQueryRunner(ABC):
    """Runs the operator's SQL read-only, from any thread."""

    @abstractmethod
    def run_console_query(self, database: ConsoleDatabase, sql: str) -> ConsoleQueryRun:
        """``sql``'s answer on ``database``, row-capped and time-limited, or why it failed."""
