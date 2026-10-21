"""S6ServiceSupervisor: port-sync kept down by its ``down`` file, amuled stopped and started by
``s6-svc``."""

from pathlib import Path

import pytest

from p2pwatch_amule.adapters.driven.s6_service_supervisor import S6ServiceSupervisor
from tests.fakes import FakeCommandRunner, FakeLogger, LoggedLine

AMULED_SERVICE_DIRECTORY = Path("/run/service/amuled")
CAPTURED = {"capture_output": True, "text": True}


@pytest.fixture
def port_sync_service_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "services.d/port-sync"
    directory.mkdir(parents=True)
    return directory


def _supervisor(
    port_sync_service_directory: Path,
    command_runner: FakeCommandRunner | None = None,
    logger: FakeLogger | None = None,
) -> S6ServiceSupervisor:
    return S6ServiceSupervisor(
        port_sync_service_directory=port_sync_service_directory,
        amuled_service_directory=AMULED_SERVICE_DIRECTORY,
        run_command=(command_runner or FakeCommandRunner()).run_command,
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
    command_runner, logger = FakeCommandRunner(), FakeLogger()

    assert _supervisor(port_sync_service_directory, command_runner, logger).stop_amuled() is True

    assert command_runner.commands == [
        (["s6-svc", "-wD", "-T", "60000", "-d", "/run/service/amuled"], CAPTURED)
    ]
    assert logger.lines == []


def test_a_stop_that_fails_is_logged(port_sync_service_directory: Path) -> None:
    command_runner, logger = FakeCommandRunner(), FakeLogger()
    command_runner.exit_code, command_runner.stderr = 99, "timed out\n"

    assert _supervisor(port_sync_service_directory, command_runner, logger).stop_amuled() is False

    assert logger.lines == [LoggedLine("error", "s6-svc -wD -T 60000 -d exited 99: timed out")]


def test_starting_amuled_sends_up(port_sync_service_directory: Path) -> None:
    command_runner, logger = FakeCommandRunner(), FakeLogger()

    _supervisor(port_sync_service_directory, command_runner, logger).start_amuled()

    assert command_runner.commands == [(["s6-svc", "-u", "/run/service/amuled"], CAPTURED)]
    assert logger.lines == []


def test_a_start_that_fails_is_logged(port_sync_service_directory: Path) -> None:
    command_runner, logger = FakeCommandRunner(), FakeLogger()
    command_runner.exit_code, command_runner.stderr = 111, "timed out\n"

    _supervisor(port_sync_service_directory, command_runner, logger).start_amuled()

    assert logger.lines == [LoggedLine("error", "s6-svc -u exited 111: timed out")]
