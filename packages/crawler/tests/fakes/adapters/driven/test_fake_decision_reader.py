import pytest

from p2pwatch.domain.file_key import FileKey, Network
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader


def test_the_decisions_refuse_a_read_the_download_loop_never_makes() -> None:
    with pytest.raises(AssertionError, match="decisions"):
        FakeDecisionReader().read_latest_decisions(FileKey(Network.ED2K, "a" * 32))
