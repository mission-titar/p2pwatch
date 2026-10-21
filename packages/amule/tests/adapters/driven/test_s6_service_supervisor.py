"""S6ServiceSupervisor: port-sync kept down by its service directory's ``down`` file."""

from pathlib import Path

import pytest

from p2pwatch_amule.adapters.driven.s6_service_supervisor import S6ServiceSupervisor


@pytest.fixture
def port_sync_service_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "services.d/port-sync"
    directory.mkdir(parents=True)
    return directory


def _supervisor(port_sync_service_directory: Path) -> S6ServiceSupervisor:
    return S6ServiceSupervisor(port_sync_service_directory=port_sync_service_directory)


@pytest.mark.parametrize("is_down_already", [False, True])
def test_disabling_port_sync_leaves_its_down_file(
    port_sync_service_directory: Path, is_down_already: bool
) -> None:
    if is_down_already:
        (port_sync_service_directory / "down").touch()

    _supervisor(port_sync_service_directory).disable_port_sync()

    assert (port_sync_service_directory / "down").is_file()


@pytest.mark.parametrize("is_down_already", [False, True])
def test_enabling_port_sync_leaves_no_down_file(
    port_sync_service_directory: Path, is_down_already: bool
) -> None:
    if is_down_already:
        (port_sync_service_directory / "down").touch()

    _supervisor(port_sync_service_directory).enable_port_sync()

    assert not (port_sync_service_directory / "down").exists()
