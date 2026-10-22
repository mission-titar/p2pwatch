from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from p2pwatch.application.ports.driven.download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.download_writer import TrackedDownloadWriter
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.repository_errors import StoreError


class FakeTrackedDownloadStore(TrackedDownloadWriter, TrackedDownloadReader):
    """In-memory downloads repo (the contract of SqliteTrackedDownloadStore, without SQL).

    Keyed by ``native_id``; ``failures`` holds the failure reasons, ``queued_at``,
    ``completed_at`` and ``seen_at`` the instants received, and ``last_seen_at`` what
    ``read_last_seen_at_by_file`` reads back.
    ``fail_set_state_for`` and ``fail_set_completed_for``: hashes for which ``set_state`` or
    ``set_completed`` raises ``StoreError``, to simulate a mid-cycle store failure
    (cf. logic-download#2/error-boundary#2).
    ``fail_tracked_states``: ``read_tracked_states()`` raises, to simulate persistence being down
    also at re-read time (every step of the cycle absorbs)."""

    def __init__(
        self,
        *,
        fail_record: bool = False,
        fail_set_state_for: set[str] | None = None,
        fail_set_completed_for: set[str] | None = None,
        fail_tracked_states: bool = False,
        fail_set_seen: bool = False,
    ) -> None:
        self.states: dict[str, DownloadState] = {}
        self.failures: dict[str, FailureReason | None] = {}
        self.sizes: dict[str, int] = {}
        self.queued_at: dict[str, datetime] = {}
        self.completed_at: dict[str, datetime] = {}
        self.seen: list[set[str]] = []
        self.seen_at: list[datetime] = []
        self.last_seen_at: dict[str, datetime] = {}
        self._fail_record = fail_record
        self._fail_set_state_for = fail_set_state_for or set()
        self._fail_set_completed_for = fail_set_completed_for or set()
        self._fail_tracked_states = fail_tracked_states
        self._fail_set_seen = fail_set_seen
        self._target_ids: dict[str, str] = {}

    def read_queued_target_id(self, file: FileKey) -> str | None:
        return self._target_ids.get(file.native_id)

    def record_queued(
        self, file: FileKey, target_id: str, size_bytes: int, queued_at: datetime
    ) -> bool:
        if self._fail_record:
            raise StoreError("downloads write failed")
        if file.native_id in self.states:
            return False
        self.states[file.native_id] = DownloadState.QUEUED
        self._target_ids[file.native_id] = target_id
        self.sizes[file.native_id] = size_bytes
        self.queued_at[file.native_id] = queued_at
        self.last_seen_at[file.native_id] = queued_at
        return True

    def set_completed(self, file: FileKey, completed_at: datetime) -> None:
        if file.native_id in self._fail_set_completed_for:
            raise StoreError(f"set_completed({file.native_id}) failed")
        self.states[file.native_id] = DownloadState.COMPLETED
        self.failures[file.native_id] = None
        self.completed_at[file.native_id] = completed_at

    def set_state(
        self,
        file: FileKey,
        state: Literal[DownloadState.DOWNLOADING, DownloadState.FAILED],
        failure_reason: FailureReason | None = None,
    ) -> None:
        if file.native_id in self._fail_set_state_for:
            raise StoreError(f"set_state({file.native_id}) failed")
        self.states[file.native_id] = state
        self.failures[file.native_id] = failure_reason

    def is_tracked(self, file: FileKey) -> bool:
        return file.native_id in self.states

    def set_seen(self, statuses: Iterable[DownloadStatus], seen_at: datetime) -> None:
        if self._fail_set_seen:
            raise StoreError("set_seen failed")
        statuses = tuple(statuses)
        self.seen.append({status.file.native_id for status in statuses})
        self.seen_at.append(seen_at)
        self.last_seen_at.update({s.file.native_id: seen_at for s in statuses})

    def read_last_seen_at_by_file(self) -> dict[FileKey, datetime]:
        return {
            FileKey(Network.ED2K, h): last_seen_at
            for h, last_seen_at in self.last_seen_at.items()
            if self.states.get(h) in {DownloadState.QUEUED, DownloadState.DOWNLOADING}
        }

    def read_tracked_states(self) -> dict[FileKey, DownloadState]:
        if self._fail_tracked_states:
            raise StoreError("read_tracked_states failed")
        return {FileKey(Network.ED2K, h): state for h, state in self.states.items()}
