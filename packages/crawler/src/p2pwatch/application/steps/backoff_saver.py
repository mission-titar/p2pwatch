"""``BackoffSaver``: the backoff the searches share, saved after each turn that changed it
(stage 2, D7)."""

from collections.abc import Iterator
from contextlib import contextmanager

from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.steps.backoff_registry import BackoffRegistry
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from p2pwatch.domain.store_error import StoreError


class BackoffSaver:
    """Holds the backoff last saved, the state the searches share."""

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
        """Wraps a turn: snapshots the backoff at the first, saves it after each that changed it."""
        if self._saved is None:
            # Once the lifecycle resumed the backoff: no save rewrites what it read.
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
