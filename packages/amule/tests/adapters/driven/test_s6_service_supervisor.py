"""S6ServiceSupervisor: port-sync kept down by its ``down`` file, amuled stopped and started by
``s6-svc``."""

import logging
from pathlib import Path

import pytest

from p2pwatch_amule.adapters.driven.s6_service_supervisor import (
    CommandRunner,
    S6ServiceSupervisor,
)
from tests.fakes.adapters.driven.fake_command_runner import FakeCommandRunner

AMULED_SERVICE_DIRECTORY = Path("/run/service/amuled")
# Not the composition's 60, so the test sees the parameter.
STOP_TIMEOUT_SECONDS = 42
CAPTURED = {"capture_output": True, "text": True}
# The module's name, which an operator's filters read (docs/migration-4x.md).
LOGGER_NAME = "p2pwatch_amule.adapters.driven.s6_service_supervisor"


@pytest.fixture
def port_sync_service_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "services.d/port-sync"
    directory.mkdir(parents=True)
    return directory


def _supervisor(
    port_sync_service_directory: Path,
    command_runner: FakeCommandRunner | None = None,
) -> S6ServiceSupervisor:
    return S6ServiceSupervisor(
        port_sync_service_directory=port_sync_service_directory,
        amuled_service_directory=AMULED_SERVICE_DIRECTORY,
        stop_timeout_seconds=STOP_TIMEOUT_SECONDS,
        run_command=(command_runner or FakeCommandRunner()).run_command,
    )


def _logged_lines(caplog: pytest.LogCaptureFixture) -> list[tuple[str, int, str]]:
    return [(record.name, record.levelno, record.getMessage()) for record in caplog.records]


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


def test_stopping_amuled_waits_until_it_is_down(
    port_sync_service_directory: Path, caplog: pytest.LogCaptureFixture
) -> None:
    command_runner = FakeCommandRunner()

    assert _supervisor(port_sync_service_directory, command_runner).stop_amuled() is True

    assert command_runner.commands == [
        (["s6-svc", "-wD", "-T", "42000", "-d", "/run/service/amuled"], CAPTURED)
    ]
    assert _logged_lines(caplog) == []


def test_a_stop_that_fails_is_logged_under_the_module_s_name(
    port_sync_service_directory: Path, caplog: pytest.LogCaptureFixture
) -> None:
    command_runner = FakeCommandRunner()
    command_runner.exit_code, command_runner.stderr = 99, "timed out\n"

    assert _supervisor(port_sync_service_directory, command_runner).stop_amuled() is False

    assert _logged_lines(caplog) == [
        (LOGGER_NAME, logging.ERROR, "s6-svc -wD -T 42000 -d exited 99: timed out")
    ]


def test_starting_amuled_sends_up(
    port_sync_service_directory: Path, caplog: pytest.LogCaptureFixture
) -> None:
    command_runner = FakeCommandRunner()

    _supervisor(port_sync_service_directory, command_runner).start_amuled()

    assert command_runner.commands == [(["s6-svc", "-u", "/run/service/amuled"], CAPTURED)]
    assert _logged_lines(caplog) == []


def test_a_start_that_fails_is_logged_under_the_module_s_name(
    port_sync_service_directory: Path, caplog: pytest.LogCaptureFixture
) -> None:
    command_runner = FakeCommandRunner()
    command_runner.exit_code, command_runner.stderr = 111, "timed out\n"

    _supervisor(port_sync_service_directory, command_runner).start_amuled()

    assert _logged_lines(caplog) == [
        (LOGGER_NAME, logging.ERROR, "s6-svc -u exited 111: timed out")
    ]


def test_mypy_refuses_a_command_runner_text_false() -> None:
    run_command: CommandRunner = FakeCommandRunner().run_command
    # The ignore is the test: strict mypy reports it unused if CommandRunner admits text=False.
    run_command(["s6-svc", "-u"], capture_output=True, text=False)  # type: ignore[arg-type]
