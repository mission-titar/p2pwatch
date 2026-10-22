"""The command line: one subcommand per driving port of the container."""

import logging

import pytest

from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch_amule.domain.settings_error import SettingsError
from tests.fakes.composition.fake_container_booter import FakeContainerBooter
from tests.fakes.composition.fake_port_sync_loop_runner import FakePortSyncLoopRunner


class _DrivingPorts:
    """The two driving ports, each recording what it was asked."""

    def __init__(self) -> None:
        self.container_booter = FakeContainerBooter()
        self.port_sync_loop_runner = FakePortSyncLoopRunner()

    def command_line(self, root_logger: logging.Logger | None = None) -> ArgparseCommandLine:
        return ArgparseCommandLine(
            container_booter=self.container_booter,
            port_sync_loop_runner=self.port_sync_loop_runner,
            root_logger=root_logger or logging.Logger("root"),
        )


def test_boot_boots_the_container_only() -> None:
    driving_ports = _DrivingPorts()

    assert driving_ports.command_line().run(["boot"]) == 0

    assert driving_ports.container_booter.boots == 1
    assert driving_ports.port_sync_loop_runner.runs == 0


def test_port_sync_runs_its_loop_only() -> None:
    driving_ports = _DrivingPorts()

    assert driving_ports.command_line().run(["port-sync"]) == 0

    assert driving_ports.port_sync_loop_runner.runs == 1
    assert driving_ports.container_booter.boots == 0


def test_a_variable_the_booter_refuses_is_printed_alone_and_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    driving_ports = _DrivingPorts()
    driving_ports.container_booter.error = SettingsError("PUID is required")

    assert driving_ports.command_line().run(["boot"]) == 1

    assert capsys.readouterr().err == "PUID is required\n"


def test_a_variable_port_sync_refuses_is_printed_alone_and_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    driving_ports = _DrivingPorts()
    driving_ports.port_sync_loop_runner.error = SettingsError(
        "PORT_SYNC_POLL_SECONDS must be a positive integer, got '0'"
    )

    assert driving_ports.command_line().run(["port-sync"]) == 1

    assert capsys.readouterr().err == "PORT_SYNC_POLL_SECONDS must be a positive integer, got '0'\n"


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    driving_ports = _DrivingPorts()

    with pytest.raises(SystemExit) as exit_info:
        driving_ports.command_line().run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: p2pwatch_amule ")
    assert driving_ports.port_sync_loop_runner.runs == 0


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _DrivingPorts().command_line().run(["--help"])

    assert exit_info.value.code == 0
    assert "{boot,port-sync}" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["boot", "port-sync"])
def test_every_subcommand_logs_at_info_with_its_logger_name(command: str) -> None:
    root_logger = logging.Logger("root")

    _DrivingPorts().command_line(root_logger).run([command])

    [handler] = root_logger.handlers
    assert handler.formatter is not None
    assert handler.formatter._fmt == "%(asctime)s %(levelname)s %(name)s %(message)s"
    assert root_logger.level == logging.INFO


def test_a_root_logger_with_a_handler_is_left_as_it_is() -> None:
    # As ``logging.basicConfig``: what configured the root logger first wins.
    root_logger = logging.Logger("root", logging.WARNING)
    handler = logging.NullHandler()
    root_logger.addHandler(handler)

    _DrivingPorts().command_line(root_logger).run(["boot"])

    assert root_logger.handlers == [handler]
    assert root_logger.level == logging.WARNING
