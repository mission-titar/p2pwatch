"""The promise of the ``TrackedDownloadReader`` and ``TrackedDownloadWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

import pytest

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network

_A = FileKey(network=Network.ED2K, native_id="a" * 32)
_B = FileKey(network=Network.ED2K, native_id="b" * 32)
_C = FileKey(network=Network.ED2K, native_id="c" * 32)
_QUEUED_AT = datetime(2026, 6, 12, 10, 0, 0, 123456, tzinfo=UTC)
_SEEN_AT = _QUEUED_AT + timedelta(hours=1)


def _status(file: FileKey) -> DownloadStatus:
    return DownloadStatus(
        file=file,
        bytes_done=0,
        size_bytes=100,
        completed=False,
        waiting_reason=None,
        failure_reason=None,
    )


class TrackedDownloadStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> TrackedDownloadWriter:
        """The writer of a store tracking no download yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> TrackedDownloadReader:
        """The reader of the writer's store."""

    def test_no_download_is_read_before_one_is_queued(self, reader: TrackedDownloadReader) -> None:
        assert reader.read_tracked_states() == {}
        assert reader.read_latest_seen_at_by_file() == {}

    def test_a_file_never_queued_is_not_tracked_and_has_no_target(
        self, reader: TrackedDownloadReader
    ) -> None:
        assert reader.is_tracked(_A) is False
        assert reader.read_queued_target_id(_A) is None

    def test_a_queued_download_is_tracked_as_queued_for_its_target(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.record_queued(_A, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT)
        assert reader.is_tracked(_A) is True
        assert reader.read_tracked_states() == {_A: DownloadState.QUEUED}
        assert reader.read_queued_target_id(_A) == "062A"

    def test_a_queued_download_never_listed_is_read_as_seen_when_queued(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.record_queued(_A, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT)
        assert reader.read_latest_seen_at_by_file() == {_A: _QUEUED_AT}

    def test_a_file_queued_again_keeps_its_row(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.record_queued(_A, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT)
        writer.set_state(_A, state=DownloadState.DOWNLOADING)
        writer.record_queued(_A, target_id=TargetId("063A"), size_bytes=200, queued_at=_SEEN_AT)
        assert (
            reader.read_queued_target_id(_A),
            reader.read_tracked_states(),
            reader.read_latest_seen_at_by_file(),
        ) == ("062A", {_A: DownloadState.DOWNLOADING}, {_A: _QUEUED_AT})

    def test_set_state_moves_each_download_to_its_state(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.record_queued(_A, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT)
        writer.record_queued(_B, target_id=TargetId("063A"), size_bytes=200, queued_at=_QUEUED_AT)
        writer.set_state(_A, state=DownloadState.DOWNLOADING)
        writer.set_state(_B, state=DownloadState.FAILED, failure_reason=FailureReason.LOST)
        assert reader.read_tracked_states() == {
            _A: DownloadState.DOWNLOADING,
            _B: DownloadState.FAILED,
        }

    def test_a_completed_download_stays_tracked_as_completed(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.record_queued(_A, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT)
        writer.set_completed(_A, completed_at=_SEEN_AT)
        assert reader.is_tracked(_A) is True
        assert reader.read_tracked_states() == {_A: DownloadState.COMPLETED}

    def test_a_listed_download_is_read_at_its_latest_listing(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.record_queued(_A, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT)
        writer.record_queued(_B, target_id=TargetId("063A"), size_bytes=200, queued_at=_QUEUED_AT)
        writer.set_state(_B, state=DownloadState.DOWNLOADING)
        writer.set_seen([_status(_B)], seen_at=_QUEUED_AT + timedelta(minutes=1))
        writer.set_seen([_status(_B)], seen_at=_SEEN_AT)
        assert reader.read_latest_seen_at_by_file() == {
            _A: _QUEUED_AT,
            _B: _SEEN_AT,
        }

    def test_the_finished_downloads_are_left_out_of_the_latest_listings(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        for file in (_A, _B, _C):
            writer.record_queued(
                file, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT
            )
        writer.set_completed(_B, completed_at=_SEEN_AT)
        writer.set_state(_C, state=DownloadState.FAILED, failure_reason=FailureReason.LOST)
        assert reader.read_latest_seen_at_by_file() == {_A: _QUEUED_AT}

    def test_a_listed_file_not_tracked_stays_untracked(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.set_seen([_status(_A)], seen_at=_SEEN_AT)
        assert reader.is_tracked(_A) is False
        assert reader.read_tracked_states() == {}
        assert reader.read_latest_seen_at_by_file() == {}

    def test_each_latest_listing_is_read_aware_in_utc(
        self, *, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        writer.record_queued(_A, target_id=TargetId("062A"), size_bytes=100, queued_at=_QUEUED_AT)
        writer.record_queued(_B, target_id=TargetId("063A"), size_bytes=200, queued_at=_QUEUED_AT)
        writer.set_seen([_status(_B)], seen_at=_SEEN_AT)
        latest_seen_ats = reader.read_latest_seen_at_by_file().values()
        assert [seen_at.utcoffset() for seen_at in latest_seen_ats] == [timedelta(0), timedelta(0)]
