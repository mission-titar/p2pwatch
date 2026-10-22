"""``python -m amule_bump``: its guard, since a test passes no process state."""

import importlib

import pytest


def test_importing_the_module_runs_no_command(capsys: pytest.CaptureFixture[str]) -> None:
    importlib.import_module("amule_bump.__main__")

    assert capsys.readouterr() == ("", "")
