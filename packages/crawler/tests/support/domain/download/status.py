"""The draws of a download's status, for the contracts that seed through
``TrackedDownloadWriter.set_seen``."""

from random import Random

from p2pwatch.domain.download.states import WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey
from tests.support.draws import draw_quantity


def draw_download_status(
    randomness: Random,
    *,
    file: FileKey,
    waiting_reason: WaitingReason | None,
    bytes_done: int | None = None,
) -> DownloadStatus:
    """``file`` listed neither completed nor failed, with ``waiting_reason``, its size and
    ``bytes_done`` drawn unless given."""
    return DownloadStatus(
        file=file,
        bytes_done=draw_quantity(randomness) if bytes_done is None else bytes_done,
        size_bytes=draw_quantity(randomness),
        completed=False,
        waiting_reason=waiting_reason,
        failure_reason=None,
    )
