"""``python -m template_checks``: the command line wired to the real checks, in the given cwd."""

from pathlib import Path

import pytest

from template_checks.__main__ import main


def test_logic_free_runs_the_logic_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.html").write_text("{% if x %}oops{% endif %}")

    assert main(["logic-free", str(tmp_path)], tmp_path) == 1

    assert capsys.readouterr().out == "bad.html:1: If is not logic-free\n"


def test_template_attributes_prints_the_attributes_of_the_templates_under_the_cwd(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "page.html").write_text("{{ row.size_mib }}{{ row.filename }}")

    assert main(["template-attributes", "templates"], tmp_path) == 0

    assert capsys.readouterr().out == "filename,size_mib\n"
