"""The promise of the ``FreeSpaceMeter`` port."""

from abc import ABC, abstractmethod

import pytest

from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError


class FreeSpaceMeterContract(ABC):
    @pytest.fixture
    @abstractmethod
    def free_space_meter(self) -> FreeSpaceMeter:
        """A meter of a directory that exists."""

    @pytest.fixture
    @abstractmethod
    def inaccessible_free_space_meter(self) -> FreeSpaceMeter:
        """A meter of a directory the filesystem refuses to examine."""

    def test_the_free_bytes_are_a_count(self, free_space_meter: FreeSpaceMeter) -> None:
        assert free_space_meter.free_bytes() >= 0

    def test_a_directory_it_cannot_examine_raises_inaccessible_path_error(
        self, inaccessible_free_space_meter: FreeSpaceMeter
    ) -> None:
        with pytest.raises(InaccessiblePathError):
            inaccessible_free_space_meter.free_bytes()
