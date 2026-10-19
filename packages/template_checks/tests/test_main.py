"""``python -m template_checks``: the command line wired to the real checks."""

from pathlib import Path

import pytest

from template_checks.__main__ import main


def test_logic_free_runs_the_logic_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.html").write_text("{% if x %}oops{% endif %}")

    assert main(["logic-free", str(tmp_path)]) == 1

    assert capsys.readouterr().out == "bad.html: forbidden tag '{% if %}'\n"


def test_read_names_prints_the_names_the_templates_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "page.html").write_text("{{ row.filename }}")

    assert main(["read-names", str(tmp_path)]) == 0

    assert capsys.readouterr().out == "filename\n"
