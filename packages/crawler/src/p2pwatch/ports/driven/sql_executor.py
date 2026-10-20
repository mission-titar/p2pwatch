"""``SqlExecutor``: runs the console's SQL on one database."""

from abc import ABC, abstractmethod
from datetime import timedelta

from p2pwatch.domain.console_query import QueryAnswer, QueryFailure


class SqlExecutor(ABC):
    """Runs one read-only statement on its database, from any thread."""

    @abstractmethod
    def execute(
        self, sql: str, *, row_cap: int, time_limit: timedelta
    ) -> QueryAnswer | QueryFailure:
        """``sql``'s first ``row_cap`` rows, or why it failed, aborted past ``time_limit``."""
