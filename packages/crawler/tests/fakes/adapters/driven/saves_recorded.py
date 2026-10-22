import sqlite3

from p2pwatch.adapters.driven.persistence_sqlite.backoff_state_repository import (
    SqliteBackoffStateRepository,
)
from p2pwatch.domain.repository_errors import RepositoryError
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState


class SavesRecorded(SqliteBackoffStateRepository):
    """Records each saved backoff map; the first ``failures`` saves raise."""

    failures = 0

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__(connection)
        self.saved: list[dict[BackoffKey, BackoffState]] = []

    def save_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None:
        if self.failures:
            self.failures -= 1
            raise RepositoryError("database is locked")
        super().save_backoff_states(backoff_state_by_key)
        self.saved.append(backoff_state_by_key)
