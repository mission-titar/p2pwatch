import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.shutil_free_space_meter import ShutilFreeSpaceMeter
from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.domain.inaccessible_path_error import InaccessiblePathError
from tests.contracts.application.ports.driven.free_space_meter_contract import (
    FreeSpaceMeterContract,
)

_UNSEARCHABLE = pytest.param(
    "unsearchable",
    marks=pytest.mark.skipif(os.geteuid() == 0, reason="root searches every directory"),
)


@pytest.fixture(params=["removed", "under a file", "name too long", _UNSEARCHABLE])
def inaccessible_directory(*, request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Path]:
    """A directory removed, one under a file, one whose name is too long, one past an
    unsearchable directory: each a real refusal of ``statvfs``."""
    match request.param:
        case "removed":
            (tmp_path / "removed").mkdir()
            (tmp_path / "removed").rmdir()
            yield tmp_path / "removed"
        case "under a file":
            (tmp_path / "file").write_bytes(b"")
            yield tmp_path / "file" / "downloads"
        case "name too long":
            yield tmp_path / ("d" * 256)
        case _:
            locked = tmp_path / "locked"
            (locked / "downloads").mkdir(parents=True)
            locked.chmod(0)
            yield locked / "downloads"
            locked.chmod(0o700)


class TestShutilFreeSpaceMeter(FreeSpaceMeterContract):
    @pytest.fixture
    def free_space_meter(self, tmp_path: Path) -> ShutilFreeSpaceMeter:
        return ShutilFreeSpaceMeter(tmp_path)

    @pytest.fixture
    def inaccessible_free_space_meter(self, inaccessible_directory: Path) -> ShutilFreeSpaceMeter:
        return ShutilFreeSpaceMeter(inaccessible_directory)


def test_reports_the_free_bytes_of_the_filesystem_holding_the_path(tmp_path: Path) -> None:
    free_space_meter: FreeSpaceMeter = ShutilFreeSpaceMeter(tmp_path)
    # The filesystem is live: the reading lies between two direct reads around it.
    before = shutil.disk_usage(tmp_path).free
    reading = free_space_meter.free_bytes()
    after = shutil.disk_usage(tmp_path).free
    assert min(before, after) <= reading <= max(before, after)


def test_the_refusal_names_the_directory_and_chains_the_system_s_error(tmp_path: Path) -> None:
    removed = tmp_path / "removed"
    with pytest.raises(InaccessiblePathError) as refusal:
        ShutilFreeSpaceMeter(removed).free_bytes()
    assert str(refusal.value) == (
        f"free space of {removed} unknown: [Errno 2] No such file or directory: '{removed}'"
    )
    assert isinstance(refusal.value.__cause__, FileNotFoundError)
