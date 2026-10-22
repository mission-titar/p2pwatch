import shutil
from pathlib import Path

from p2pwatch.adapters.driven.shutil_free_space_meter import ShutilFreeSpaceMeter
from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter


def test_reports_the_free_bytes_of_the_filesystem_holding_the_path(tmp_path: Path) -> None:
    free_space_meter: FreeSpaceMeter = ShutilFreeSpaceMeter(tmp_path)
    assert free_space_meter.free_bytes() == shutil.disk_usage(tmp_path).free
