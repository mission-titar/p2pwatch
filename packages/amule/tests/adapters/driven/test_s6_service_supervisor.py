"""S6ServiceSupervisor: port-sync kept down by its ``down`` file, amuled stopped and started by
``s6-svc``."""

import subprocess
from pathlib import Path
from typing import Any

import pytest

from p2pwatch_amule.adapters.driven.s6_service_supervisor import S6ServiceSupervisor
from tests.fakes import FakeLogger, LoggedLine

AMULED_SERVICE_DIRECTORY = Path("/run/service/amuled")


class FakeS6:
    """Records the commands run, each exiting ``exit_code``: the gate runs no s6."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.exit_code = 0

    def run_command(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs == {"capture_output": True, "text": True}
        self.commands.append(argv)
        return subprocess.CompletedProcess(argv, self.exit_code, "", "timed out\n")


@pytest.fixture
def port_sync_service_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "services.d/port-sync"
    directory.mkdir(parents=True)
    return directory


def _supervisor(
    port_sync_service_directory: Path,
    s6: FakeS6 | None = None,
    logger: FakeLogger | None = None,
) -> S6ServiceSupervisor:
    return S6ServiceSupervisor(
        port_sync_service_directory=port_sync_service_directory,
        amuled_service_directory=AMULED_SERVICE_DIRECTORY,
        run_command=(s6 or FakeS6()).run_command,
        logger=logger or FakeLogger(),
    )


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


def test_stopping_amuled_waits_until_it_is_down(port_sync_service_directory: Path) -> None:
    s6, logger = FakeS6(), FakeLogger()

    assert _supervisor(port_sync_service_directory, s6, logger).stop_amuled() is True

    assert s6.commands == [["s6-svc", "-wD", "-T", "60000", "-d", "/run/service/amuled"]]
    assert logger.lines == []


def test_a_stop_that_fails_is_logged(port_sync_service_directory: Path) -> None:
    s6, logger = FakeS6(), FakeLogger()
    s6.exit_code = 99

    assert _supervisor(port_sync_service_directory, s6, logger).stop_amuled() is False

    assert logger.lines == [LoggedLine("error", "s6-svc -wD -T 60000 -d exited 99: timed out")]


def test_starting_amuled_sends_up(port_sync_service_directory: Path) -> None:
    s6, logger = FakeS6(), FakeLogger()

    _supervisor(port_sync_service_directory, s6, logger).start_amuled()

    assert s6.commands == [["s6-svc", "-u", "/run/service/amuled"]]
    assert logger.lines == []


def test_a_start_that_fails_is_logged(port_sync_service_directory: Path) -> None:
    s6, logger = FakeS6(), FakeLogger()
    s6.exit_code = 111

    _supervisor(port_sync_service_directory, s6, logger).start_amuled()

    assert logger.lines == [LoggedLine("error", "s6-svc -u exited 111: timed out")]
