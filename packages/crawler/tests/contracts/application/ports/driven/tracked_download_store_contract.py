"""The promise of the ``TrackedDownloadReader`` and ``TrackedDownloadWriter`` pair."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol

import pytest

from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network

_A = FileKey(Network.ED2K, "a" * 32)
_B = FileKey(Network.ED2K, "b" * 32)
_C = FileKey(Network.ED2K, "c" * 32)
_QUEUED_AT = datetime(2026, 6, 12, 10, 0, 0, 123456, tzinfo=UTC)
_SEEN_AT = _QUEUED_AT + timedelta(hours=1)


def _status(file: FileKey) -> DownloadStatus:
    return DownloadStatus(file, 0, 100, False, None, None)


class TrackedDownloadStore(Protocol):
    """Both ports of the pair, which one store implements."""

    def record_queued(
        self, file: FileKey, target_id: str, size_bytes: int, queued_at: datetime
    ) -> None: ...

    def set_completed(self, file: FileKey, completed_at: datetime) -> None: ...

    def set_state(
        self,
        file: FileKey,
        state: Literal[DownloadState.DOWNLOADING, DownloadState.FAILED],
        failure_reason: FailureReason | None = None,
    ) -> None: ...

    def set_seen(self, statuses: Iterable[DownloadStatus], seen_at: datetime) -> None: ...

    def is_tracked(self, file: FileKey) -> bool: ...

    def read_latest_seen_at_by_file(self) -> dict[FileKey, datetime]: ...

    def read_tracked_states(self) -> dict[FileKey, DownloadState]: ...

    def read_queued_target_id(self, file: FileKey) -> str | None: ...


class TrackedDownloadStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def tracked_download_store(self) -> TrackedDownloadStore:
        """A store tracking no download yet."""

    def test_no_download_is_read_before_one_is_queued(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        assert tracked_download_store.read_tracked_states() == {}
        assert tracked_download_store.read_latest_seen_at_by_file() == {}

    def test_a_file_never_queued_is_not_tracked_and_has_no_target(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        assert tracked_download_store.is_tracked(_A) is False
        assert tracked_download_store.read_queued_target_id(_A) is None

    def test_a_queued_download_is_tracked_as_queued_for_its_target(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.record_queued(_A, "062A", 100, _QUEUED_AT)
        assert tracked_download_store.is_tracked(_A) is True
        assert tracked_download_store.read_tracked_states() == {_A: DownloadState.QUEUED}
        assert tracked_download_store.read_queued_target_id(_A) == "062A"

    def test_a_queued_download_never_listed_is_read_as_last_listed_when_queued(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.record_queued(_A, "062A", 100, _QUEUED_AT)
        assert tracked_download_store.read_latest_seen_at_by_file() == {_A: _QUEUED_AT}

    def test_a_file_queued_again_keeps_its_row(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.record_queued(_A, "062A", 100, _QUEUED_AT)
        tracked_download_store.set_state(_A, DownloadState.DOWNLOADING)
        tracked_download_store.record_queued(_A, "063A", 200, _SEEN_AT)
        assert (
            tracked_download_store.read_queued_target_id(_A),
            tracked_download_store.read_tracked_states(),
            tracked_download_store.read_latest_seen_at_by_file(),
        ) == ("062A", {_A: DownloadState.DOWNLOADING}, {_A: _QUEUED_AT})

    def test_set_state_moves_each_download_to_its_state(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.record_queued(_A, "062A", 100, _QUEUED_AT)
        tracked_download_store.record_queued(_B, "063A", 200, _QUEUED_AT)
        tracked_download_store.set_state(_A, DownloadState.DOWNLOADING)
        tracked_download_store.set_state(_B, DownloadState.FAILED, FailureReason.LOST)
        assert tracked_download_store.read_tracked_states() == {
            _A: DownloadState.DOWNLOADING,
            _B: DownloadState.FAILED,
        }

    def test_a_completed_download_stays_tracked_as_completed(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.record_queued(_A, "062A", 100, _QUEUED_AT)
        tracked_download_store.set_completed(_A, _SEEN_AT)
        assert tracked_download_store.is_tracked(_A) is True
        assert tracked_download_store.read_tracked_states() == {_A: DownloadState.COMPLETED}

    def test_a_listed_download_is_read_as_last_listed_at_its_latest_stamp(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.record_queued(_A, "062A", 100, _QUEUED_AT)
        tracked_download_store.record_queued(_B, "063A", 200, _QUEUED_AT)
        tracked_download_store.set_state(_B, DownloadState.DOWNLOADING)
        tracked_download_store.set_seen([_status(_B)], _QUEUED_AT + timedelta(minutes=1))
        tracked_download_store.set_seen([_status(_B)], _SEEN_AT)
        assert tracked_download_store.read_latest_seen_at_by_file() == {
            _A: _QUEUED_AT,
            _B: _SEEN_AT,
        }

    def test_the_finished_downloads_are_left_out_of_the_latest_listings(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        for file in (_A, _B, _C):
            tracked_download_store.record_queued(file, "062A", 100, _QUEUED_AT)
        tracked_download_store.set_completed(_B, _SEEN_AT)
        tracked_download_store.set_state(_C, DownloadState.FAILED, FailureReason.LOST)
        assert tracked_download_store.read_latest_seen_at_by_file() == {_A: _QUEUED_AT}

    def test_a_listed_file_not_tracked_stays_untracked(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.set_seen([_status(_A)], _SEEN_AT)
        assert tracked_download_store.is_tracked(_A) is False
        assert tracked_download_store.read_tracked_states() == {}
        assert tracked_download_store.read_latest_seen_at_by_file() == {}

    def test_each_latest_listing_is_read_aware_in_utc(
        self, tracked_download_store: TrackedDownloadStore
    ) -> None:
        tracked_download_store.record_queued(_A, "062A", 100, _QUEUED_AT)
        tracked_download_store.record_queued(_B, "063A", 200, _QUEUED_AT)
        tracked_download_store.set_seen([_status(_B)], _SEEN_AT)
        latest_seen_ats = tracked_download_store.read_latest_seen_at_by_file().values()
        assert [seen_at.utcoffset() for seen_at in latest_seen_ats] == [timedelta(0), timedelta(0)]
