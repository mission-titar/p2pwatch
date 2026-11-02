"""The promise of the ``TrackedDownloadReader`` and ``TrackedDownloadWriter`` pair."""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from random import Random

import pytest

from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.file_key import FileKey
from tests.support.domain.download.status import draw_download_status
from tests.support.domain.file_target_decision import draw_target_id
from tests.support.domain.observation import draw_file
from tests.support.draws import draw_instant, draw_instants, draw_quantity


def _draw_queued_file(
    randomness: Random, *, writer: TrackedDownloadWriter, queued_at: datetime
) -> FileKey:
    """A drawn file, once ``writer`` has queued it at ``queued_at`` for a drawn target."""
    file = draw_file(randomness)
    writer.record_queued(
        file,
        target_id=draw_target_id(randomness),
        size_bytes=draw_quantity(randomness),
        queued_at=queued_at,
    )
    return file


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
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        _draw_queued_file(randomness, writer=writer, queued_at=draw_instant(randomness))
        file = draw_file(randomness)
        assert reader.is_tracked(file) is False
        assert reader.read_queued_target_id(file) is None

    def test_each_queued_download_is_tracked_as_queued_for_its_target(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        target_id_by_file = {draw_file(randomness): draw_target_id(randomness) for _ in range(2)}
        for file, target_id in target_id_by_file.items():
            writer.record_queued(
                file,
                target_id=target_id,
                size_bytes=draw_quantity(randomness),
                queued_at=draw_instant(randomness),
            )
        assert all(reader.is_tracked(file) for file in target_id_by_file)
        assert reader.read_tracked_states() == dict.fromkeys(
            target_id_by_file, DownloadState.QUEUED
        )
        assert {
            file: reader.read_queued_target_id(file) for file in target_id_by_file
        } == target_id_by_file

    def test_a_queued_download_never_listed_is_read_as_seen_when_queued(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        queued_at = draw_instant(randomness)
        file = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        assert reader.read_latest_seen_at_by_file() == {file: queued_at}

    def test_a_file_queued_again_keeps_its_row(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        queued_at, queued_again_at = draw_instants(randomness, count=2)
        file, target_id = draw_file(randomness), draw_target_id(randomness)
        writer.record_queued(
            file, target_id=target_id, size_bytes=draw_quantity(randomness), queued_at=queued_at
        )
        writer.set_state(file, state=DownloadState.DOWNLOADING)
        writer.record_queued(
            file,
            target_id=draw_target_id(randomness),
            size_bytes=draw_quantity(randomness),
            queued_at=queued_again_at,
        )
        assert (
            reader.read_queued_target_id(file),
            reader.read_tracked_states(),
            reader.read_latest_seen_at_by_file(),
        ) == (target_id, {file: DownloadState.DOWNLOADING}, {file: queued_at})

    def test_set_state_moves_each_download_to_its_state(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        queued_at = draw_instant(randomness)
        downloading = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        failed = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        writer.set_state(downloading, state=DownloadState.DOWNLOADING)
        writer.set_state(failed, state=DownloadState.FAILED, failure_reason=FailureReason.LOST)
        assert reader.read_tracked_states() == {
            downloading: DownloadState.DOWNLOADING,
            failed: DownloadState.FAILED,
        }

    def test_a_completed_download_stays_tracked_as_completed(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        queued_at, completed_at = draw_instants(randomness, count=2)
        file = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        writer.set_completed(file, completed_at=completed_at)
        assert reader.is_tracked(file) is True
        assert reader.read_tracked_states() == {file: DownloadState.COMPLETED}

    def test_a_listed_download_is_read_at_its_latest_listing(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        queued_at, listed_at, listed_again_at = draw_instants(randomness, count=3)
        never_listed = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        listed = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        writer.set_state(listed, state=DownloadState.DOWNLOADING)
        for seen_at in (listed_at, listed_again_at):
            status = draw_download_status(randomness, file=listed, waiting_reason=None)
            writer.set_seen([status], seen_at=seen_at)
        assert reader.read_latest_seen_at_by_file() == {
            never_listed: queued_at,
            listed: listed_again_at,
        }

    def test_the_finished_downloads_are_left_out_of_the_latest_listings(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        queued_at, completed_at = draw_instants(randomness, count=2)
        queued = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        completed = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        failed = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        writer.set_completed(completed, completed_at=completed_at)
        writer.set_state(failed, state=DownloadState.FAILED, failure_reason=FailureReason.LOST)
        assert reader.read_latest_seen_at_by_file() == {queued: queued_at}

    def test_a_listed_file_not_tracked_stays_untracked(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        file = draw_file(randomness)
        status = draw_download_status(randomness, file=file, waiting_reason=None)
        writer.set_seen([status], seen_at=draw_instant(randomness))
        assert reader.is_tracked(file) is False
        assert reader.read_tracked_states() == {}
        assert reader.read_latest_seen_at_by_file() == {}

    def test_each_latest_listing_is_read_aware_in_utc(
        self, *, randomness: Random, writer: TrackedDownloadWriter, reader: TrackedDownloadReader
    ) -> None:
        queued_at, listed_at = draw_instants(randomness, count=2)
        _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        listed = _draw_queued_file(randomness, writer=writer, queued_at=queued_at)
        status = draw_download_status(randomness, file=listed, waiting_reason=None)
        writer.set_seen([status], seen_at=listed_at)
        latest_seen_ats = reader.read_latest_seen_at_by_file().values()
        assert [seen_at.utcoffset() for seen_at in latest_seen_ats] == [UTC.utcoffset(None)] * 2
