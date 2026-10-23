"""Starts every download the client does not list."""

from p2pwatch.application.steps.download_deps import DownloadDeps
from p2pwatch.domain.client_errors import DownloadRejectedError
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.states import DownloadState, FailureReason
from p2pwatch.domain.file_key import FileKey


async def start_unlisted(deps: DownloadDeps, listed_files: frozenset[FileKey]) -> None:
    """Starts every ``queued`` or ``downloading`` download the client does not list (D13).

    A new download and a forgotten one are the same case. ``DownloadRejectedError`` fails THAT
    download, since retrying would resend a refused request; ``ClientUnreachableError``
    propagates and the caller skips the iteration.
    """
    # FRESH re-read: queue_new_candidates wrote new QUEUED rows this cycle.
    states = deps.tracked_download_reader.read_tracked_states()
    for file, state in states.items():
        if state not in {DownloadState.QUEUED, DownloadState.DOWNLOADING} or file in listed_files:
            continue
        observation = deps.observation_reader.read_latest_observation(file)
        if observation is None:
            continue
        reported_file = observation.reported_file
        try:
            await deps.download_client.start(
                DownloadRequest(file, reported_file.filename, reported_file.size_bytes)
            )
        except DownloadRejectedError as error:
            deps.tracked_download_writer.set_state(
                file, DownloadState.FAILED, FailureReason.REJECTED
            )
            deps.logger.warning(
                "start rejected by the client for file=%s (%s): marked failed",
                file.native_id,
                error,
            )
