import pytest

from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.file_key import FileKey, Network
from tests.fakes.adapters.driven.fake_no_set_state_tracked_download_store import (
    FakeNoSetStateTrackedDownloadStore,
)


def test_the_store_refuses_the_state_change_a_cycle_never_makes() -> None:
    with pytest.raises(AssertionError, match="set_state"):
        FakeNoSetStateTrackedDownloadStore().set_state(
            FileKey(network=Network.ED2K, native_id="a" * 32), state=DownloadState.FAILED
        )
