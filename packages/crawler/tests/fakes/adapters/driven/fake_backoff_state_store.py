from p2pwatch.application.ports.driven.backoff_state_reader import BackoffStateReader
from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.domain.repository_errors import RepositoryError
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState


class FakeBackoffStateStore(BackoffStateReader, BackoffStateWriter):
    """Keeps the latest backoff map saved, and each one; the first ``failures`` saves raise."""

    def __init__(self) -> None:
        self.failures = 0
        self.saved: list[dict[BackoffKey, BackoffState]] = []
        self._backoff_state_by_key: dict[BackoffKey, BackoffState] = {}

    def read_backoff_states(self) -> dict[BackoffKey, BackoffState]:
        return dict(self._backoff_state_by_key)

    def save_backoff_states(self, backoff_state_by_key: dict[BackoffKey, BackoffState]) -> None:
        if self.failures:
            self.failures -= 1
            raise RepositoryError("database is locked")
        self._backoff_state_by_key = dict(backoff_state_by_key)
        self.saved.append(backoff_state_by_key)
