"""The command line, wired to the real checks, in the given cwd."""

from pathlib import Path

import pytest

from template_checks.composition.command_line import build_command_line


def test_logic_free_runs_the_logic_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.html").write_text("{% if x %}oops{% endif %}")

    assert build_command_line(cwd=tmp_path).run(["logic-free", str(tmp_path)]) == 1

    assert capsys.readouterr().out == "bad.html:1: If is not logic-free\n"


def test_template_attributes_prints_the_attributes_of_the_templates_under_the_cwd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "page.html").write_text("{{ row.size_mib }}{{ row.filename }}")

    assert build_command_line(cwd=tmp_path).run(["template-attributes", "templates"]) == 0

    assert capsys.readouterr().out == "filename,size_mib\n"
