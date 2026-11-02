from random import Random

from p2pwatch.domain.download.states import WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from tests.support.domain.download.status import draw_download_status
from tests.support.domain.observation import draw_file
from tests.support.draws import draw_quantity


def _drawn(seed: int) -> DownloadStatus:
    randomness = Random(seed)
    return draw_download_status(randomness, file=draw_file(randomness), waiting_reason=None)


def test_a_drawn_status_is_neither_completed_nor_failed() -> None:
    status = _drawn(0)
    assert (status.completed, status.failure_reason) == (False, None)


def test_a_drawn_status_keeps_what_its_test_relates() -> None:
    randomness = Random(0)
    file = draw_file(randomness)
    bytes_done = draw_quantity(randomness)
    status = draw_download_status(
        randomness, file=file, waiting_reason=WaitingReason.PAUSED, bytes_done=bytes_done
    )
    assert (status.file, status.waiting_reason, status.bytes_done) == (
        file,
        WaitingReason.PAUSED,
        bytes_done,
    )


def test_the_same_seed_draws_the_same_status() -> None:
    assert _drawn(7) == _drawn(7)
