"""Starts every download the client does not list."""

from p2pwatch.application.ports.driven.download_client import DownloadClient
from p2pwatch.application.ports.driven.logger import Logger
from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.tracked_download_reader import TrackedDownloadReader
from p2pwatch.application.ports.driven.tracked_download_writer import TrackedDownloadWriter
from p2pwatch.domain.client_errors import DownloadRejectedError
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.file_key import FileKey


class DownloadStarter:
    """Makes the client hold every queued or downloading download it does not list."""

    def __init__(
        self,
        *,
        download_client: DownloadClient,
        tracked_download_writer: TrackedDownloadWriter,
        tracked_download_reader: TrackedDownloadReader,
        observation_reader: ObservationReader,
        logger: Logger,
    ) -> None:
        self._download_client = download_client
        self._tracked_download_writer = tracked_download_writer
        self._tracked_download_reader = tracked_download_reader
        self._observation_reader = observation_reader
        self._logger = logger

    async def start_unlisted(self, listed_files: frozenset[FileKey]) -> None:
        """Starts every ``queued`` or ``downloading`` download the client does not list (D13).

        A new download and a forgotten one are the same case. ``DownloadRejectedError`` fails THAT
        download, since retrying would resend a refused request; ``ClientUnreachableError``
        propagates and the caller skips the iteration.
        """
        # FRESH re-read: queue_new_candidates wrote new QUEUED rows this cycle.
        states = self._tracked_download_reader.read_tracked_states()
        for file, state in states.items():
            if (
                state not in {DownloadState.QUEUED, DownloadState.DOWNLOADING}
                or file in listed_files
            ):
                continue
            observation = self._observation_reader.read_latest_observation(file)
            if observation is None:
                continue
            reported_file = observation.reported_file
            try:
                await self._download_client.start(
                    DownloadRequest(file, reported_file.filename, reported_file.size_bytes)
                )
            except DownloadRejectedError as error:
                self._tracked_download_writer.set_state(
                    file, DownloadState.FAILED, FailureReason.REJECTED
                )
                self._logger.warning(
                    "start rejected by the client for file=%s (%s): marked failed",
                    file.native_id,
                    error,
                )
