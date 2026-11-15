"""``BackoffSaver``: sets the backoff in its store after each search that changed it, so a node
restarted while Kad refuses its searches waits out what is left of Kad's backoff."""

from collections.abc import Iterator
from contextlib import contextmanager

from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.backoff_registry import BackoffRegistry
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from p2pwatch.domain.store_error import StoreError


class BackoffSaver:
    """Saves the backoff every search shares, one saver for all of them, after each search whose
    failure or success changed it."""

    def __init__(
        self,
        *,
        backoff: BackoffRegistry,
        backoff_state_writer: BackoffStateWriter,
        logger: Logger,
    ) -> None:
        self._backoff = backoff
        self._backoff_state_writer = backoff_state_writer
        self._logger = logger
        self._saved: dict[BackoffKey, BackoffState] | None = None

    @contextmanager
    def saving(self) -> Iterator[None]:
        """Wraps one search, then sets the backoff in the store if it differs from the one last
        saved."""
        if self._saved is None:
            # At the first search, once the start resumed the saved backoff, so none is rewritten.
            self._saved = self._backoff.snapshot()
        yield
        self._save()

    def _save(self) -> None:
        current = self._backoff.snapshot()
        if current == self._saved:
            return
        try:
            self._backoff_state_writer.set_backoff_states(current)
        except StoreError as error:
            self._logger.error("backoff not saved (%s): retried after the next search", error)
            return
        self._saved = current
