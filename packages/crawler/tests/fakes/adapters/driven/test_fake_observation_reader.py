import pytest

from p2pwatch.domain.file_key import FileKey, Network
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader


def test_the_filenames_refuse_a_read_the_download_loop_never_makes() -> None:
    with pytest.raises(AssertionError, match="filenames"):
        FakeObservationReader().read_known_filenames(FileKey(Network.ED2K, "a" * 32))
