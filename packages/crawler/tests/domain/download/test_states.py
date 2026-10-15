from p2pwatch.domain.download.states import DownloadState


def test_states_are_a_closed_enum() -> None:
    assert set(DownloadState) == {
        DownloadState.QUEUED,
        DownloadState.DOWNLOADING,
        DownloadState.COMPLETED,
        DownloadState.FAILED,
    }


def test_state_values_are_stable_strings() -> None:
    assert DownloadState.QUEUED.value == "queued"
    assert DownloadState.COMPLETED.value == "completed"
