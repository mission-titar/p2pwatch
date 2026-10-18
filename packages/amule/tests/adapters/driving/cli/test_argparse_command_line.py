"""The command line: one subcommand per entry point of the container."""

import logging

import pytest

from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


class _EntryPoints:
    """Records which entry point each run called."""

    def __init__(self) -> None:
        self.called: list[str] = []

    def command_line(self) -> ArgparseCommandLine:
        return ArgparseCommandLine(
            boot=lambda: self.called.append("boot"),
            sync_listen_port=lambda: self.called.append("port-sync"),
        )


@pytest.mark.parametrize("command", ["boot", "port-sync"])
def test_a_subcommand_runs_its_entry_point_only(command: str) -> None:
    entry_points = _EntryPoints()

    entry_points.command_line().run([command])

    assert entry_points.called == [command]


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    entry_points = _EntryPoints()

    with pytest.raises(SystemExit) as exit_info:
        entry_points.command_line().run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: p2pwatch_amule ")
    assert entry_points.called == []


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _EntryPoints().command_line().run(["--help"])

    assert exit_info.value.code == 0
    assert "{boot,port-sync}" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["boot", "port-sync"])
def test_every_subcommand_logs_at_info_with_its_logger_name(
    command: str, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    root = logging.getLogger()
    root_level = root.level
    request.addfinalizer(lambda: root.setLevel(root_level))
    monkeypatch.setattr(root, "handlers", [])  # pytest's own, which basicConfig would keep

    _EntryPoints().command_line().run([command])

    [handler] = root.handlers
    assert handler.formatter is not None
    assert handler.formatter._fmt == "%(asctime)s %(levelname)s %(name)s %(message)s"
    assert root.level == logging.INFO
