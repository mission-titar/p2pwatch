"""The command line, wired to the real checks, in the given cwd."""

from pathlib import Path

import pytest

from template_checks.composition.command_line import build_command_line


def test_logic_free_runs_the_logic_check(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.html").write_text("{% if x %}oops{% endif %}")

    assert build_command_line(cwd=tmp_path).run(["logic-free", str(tmp_path)]) == 1

    assert capsys.readouterr().out == f"{tmp_path / 'bad.html'}:1: If is not logic-free\n"


def test_template_attributes_prints_the_attributes_of_the_templates_under_the_cwd(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "page.html").write_text("{{ row.size_mib }}{{ row.filename }}")

    assert build_command_line(cwd=tmp_path).run(["template-attributes", "templates"]) == 0

    assert capsys.readouterr().out == "filename,size_mib\n"


@pytest.mark.parametrize("command", ["logic-free", "template-attributes"])
def test_a_template_jinja_cannot_parse_ends_in_one_error_line_naming_it(
    *, command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "page.html").write_text("<p>\n{% if %}")

    assert build_command_line(cwd=tmp_path).run([command, "templates"]) == 1

    assert capsys.readouterr() == (
        "",
        f"error: {tmp_path / 'templates/page.html'}:2: Expected an expression, got 'end of"
        " statement block'\n",
    )


def test_an_absent_templates_directory_ends_in_one_error_line_naming_it(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert build_command_line(cwd=tmp_path).run(["template-attributes", "absent"]) == 1

    assert capsys.readouterr() == ("", f"error: {tmp_path}/absent: No such file or directory\n")
