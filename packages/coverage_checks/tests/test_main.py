"""``python -m coverage_checks``: its guard, since a test passes no process state."""

import importlib

import pytest


def test_importing_the_module_runs_no_command(capsys: pytest.CaptureFixture[str]) -> None:
    importlib.import_module("coverage_checks.__main__")

    assert capsys.readouterr() == ("", "")
