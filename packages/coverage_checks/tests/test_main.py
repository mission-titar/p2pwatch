"""``python -m coverage_checks``: the command line wired to the real check."""

from pathlib import Path

import pytest

from coverage_checks.__main__ import main


def test_unit_coverage_runs_the_check_in_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["unit-coverage"]) == 1

    assert capsys.readouterr().err.startswith("no per-test branch coverage in .coverage")
