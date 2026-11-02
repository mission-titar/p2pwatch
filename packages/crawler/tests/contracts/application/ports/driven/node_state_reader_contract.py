"""The promise of ``NodeStateReader``."""

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime
from random import Random

import pytest

from p2pwatch.application.ports.driven.backoff_state_writer import BackoffStateWriter
from p2pwatch.application.ports.driven.node_id_writer import NodeIdWriter
from p2pwatch.application.ports.driven.node_state_reader import NodeStateReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.node_state import NodeState, TrackedDownload
from tests.support.domain.download.status import draw_download_status
from tests.support.domain.file_target_decision import draw_target_id
from tests.support.domain.observation import draw_file
from tests.support.domain.search.backoff import draw_backoff_key, draw_backoff_state
from tests.support.draws import (
    draw_instant,
    draw_instants,
    draw_quantities,
    draw_quantity,
    draw_text,
)


def _queue(
    randomness: Random, *, writer: TrackedDownloadWriter, file: FileKey, queued_at: datetime
) -> TrackedDownload:
    """``file`` queued at ``queued_at`` for a drawn target, as it is read before any listing."""
    target_id = draw_target_id(randomness)
    writer.record_queued(
        file, target_id=target_id, size_bytes=draw_quantity(randomness), queued_at=queued_at
    )
    return TrackedDownload(
        file=file,
        target_id=target_id,
        state=DownloadState.QUEUED,
        queued_at=queued_at,
        completed_at=None,
        latest_progress_at=None,
        waiting_reason=None,
        failure_reason=None,
    )


class NodeStateReaderContract(ABC):
    @pytest.fixture
    @abstractmethod
    def node_id_writer(self) -> NodeIdWriter:
        """The writer of the node id of a node holding no state yet."""

    @pytest.fixture
    @abstractmethod
    def tracked_download_writer(self) -> TrackedDownloadWriter:
        """The writer of the tracked downloads of the node id writer's node."""

    @pytest.fixture
    @abstractmethod
    def backoff_state_writer(self) -> BackoffStateWriter:
        """The writer of the backoff states of the node id writer's node."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> NodeStateReader:
        """The reader of the writers' node."""

    def test_a_node_that_recorded_nothing_has_no_id_no_download_and_no_backoff(
        self, reader: NodeStateReader
    ) -> None:
        assert reader.read_node_state() == NodeState(
            node_id=None, created_at=None, downloads=(), backoff_state_by_key={}
        )

    def test_the_node_id_is_read_with_its_creation(
        self, *, randomness: Random, node_id_writer: NodeIdWriter, reader: NodeStateReader
    ) -> None:
        node_id, created_at = NodeId(draw_text(randomness)), draw_instant(randomness)
        node_id_writer.record_node_id(node_id, created_at=created_at)
        node_state = reader.read_node_state()
        assert (node_state.node_id, node_state.created_at) == (node_id, created_at)

    def test_the_downloads_are_read_by_when_they_were_queued_then_by_native_id(
        self,
        *,
        randomness: Random,
        tracked_download_writer: TrackedDownloadWriter,
        reader: NodeStateReader,
    ) -> None:
        earlier_at, later_at = draw_instants(randomness, count=2)
        lowest, middle, highest = sorted(
            (draw_file(randomness) for _ in range(3)), key=lambda file: file.native_id
        )
        # Queued in neither order, the earliest holding the highest native id.
        writer = tracked_download_writer
        queued_middle = _queue(randomness, writer=writer, file=middle, queued_at=later_at)
        queued_highest = _queue(randomness, writer=writer, file=highest, queued_at=earlier_at)
        queued_lowest = _queue(randomness, writer=writer, file=lowest, queued_at=later_at)
        assert reader.read_node_state().downloads == (queued_highest, queued_lowest, queued_middle)

    def test_a_download_s_latest_progress_is_its_latest_listing_whose_bytes_grew(
        self,
        *,
        randomness: Random,
        tracked_download_writer: TrackedDownloadWriter,
        reader: NodeStateReader,
    ) -> None:
        queued_at, listed_at, grown_at, listed_again_at = draw_instants(randomness, count=4)
        queued = _queue(
            randomness,
            writer=tracked_download_writer,
            file=draw_file(randomness),
            queued_at=queued_at,
        )
        fewer_bytes, more_bytes = draw_quantities(randomness, count=2)
        for bytes_done, seen_at in [
            (fewer_bytes, listed_at),
            (more_bytes, grown_at),
            (more_bytes, listed_again_at),
        ]:
            status = draw_download_status(
                randomness, file=queued.file, waiting_reason=None, bytes_done=bytes_done
            )
            tracked_download_writer.set_seen([status], seen_at=seen_at)
        assert reader.read_node_state().downloads == (replace(queued, latest_progress_at=grown_at),)

    def test_a_failed_download_is_read_with_its_reasons_as_the_domain_s_members(
        self,
        *,
        randomness: Random,
        tracked_download_writer: TrackedDownloadWriter,
        reader: NodeStateReader,
    ) -> None:
        queued_at, listed_at = draw_instants(randomness, count=2)
        queued = _queue(
            randomness,
            writer=tracked_download_writer,
            file=draw_file(randomness),
            queued_at=queued_at,
        )
        status = draw_download_status(
            randomness, file=queued.file, waiting_reason=WaitingReason.NO_SOURCE
        )
        tracked_download_writer.set_seen([status], seen_at=listed_at)
        tracked_download_writer.set_state(
            queued.file, state=DownloadState.FAILED, failure_reason=FailureReason.ERROR
        )
        (download,) = reader.read_node_state().downloads
        assert download == replace(
            queued,
            state=DownloadState.FAILED,
            latest_progress_at=listed_at,
            waiting_reason=WaitingReason.NO_SOURCE,
            failure_reason=FailureReason.ERROR,
        )
        # A StrEnum equals its text: only the types tell a member from it.
        members = (download.state, download.waiting_reason, download.failure_reason)
        assert [type(member) for member in members] == [DownloadState, WaitingReason, FailureReason]

    def test_a_completed_download_is_read_at_its_completion(
        self,
        *,
        randomness: Random,
        tracked_download_writer: TrackedDownloadWriter,
        reader: NodeStateReader,
    ) -> None:
        queued_at, listed_at, completed_at = draw_instants(randomness, count=3)
        queued = _queue(
            randomness,
            writer=tracked_download_writer,
            file=draw_file(randomness),
            queued_at=queued_at,
        )
        status = draw_download_status(randomness, file=queued.file, waiting_reason=None)
        tracked_download_writer.set_seen([status], seen_at=listed_at)
        tracked_download_writer.set_completed(queued.file, completed_at=completed_at)
        assert reader.read_node_state().downloads == (
            replace(
                queued,
                state=DownloadState.COMPLETED,
                completed_at=completed_at,
                latest_progress_at=listed_at,
            ),
        )

    def test_the_backoffs_are_read_by_client_each_whole_client_backoff_before_its_channels(
        self,
        *,
        randomness: Random,
        backoff_state_writer: BackoffStateWriter,
        reader: NodeStateReader,
    ) -> None:
        first_client, second_client = sorted(
            (draw_backoff_key(randomness, has_channel=False) for _ in range(2)),
            key=lambda whole_client: whole_client.client_name,
        )
        first_client_channels = sorted(
            (
                draw_backoff_key(randomness, has_channel=True, client_name=first_client.client_name)
                for _ in range(2)
            ),
            key=lambda channel: str(channel.channel),
        )
        keys_in_order = [
            first_client,
            *first_client_channels,
            second_client,
            draw_backoff_key(randomness, has_channel=True, client_name=second_client.client_name),
        ]
        backoff_state_by_key = {key: draw_backoff_state(randomness) for key in keys_in_order}
        # Saved in the reverse order, so a read in the order saved fails too.
        backoff_state_writer.set_backoff_states(dict(reversed(backoff_state_by_key.items())))
        backoff_states = reader.read_node_state().backoff_state_by_key.items()
        assert list(backoff_states) == list(backoff_state_by_key.items())
