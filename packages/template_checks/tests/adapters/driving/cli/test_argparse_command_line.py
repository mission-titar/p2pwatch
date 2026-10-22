"""The command line: one subcommand per check, over a templates directory taken under ``cwd``."""

from pathlib import Path

import pytest

from template_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from tests.fakes.application.use_cases.fake_logic_free_checker import FakeLogicFreeChecker
from tests.fakes.application.use_cases.fake_template_attribute_lister import (
    FakeTemplateAttributeLister,
)

_CWD = Path("/work")


def _command_line(
    logic_free_checker: FakeLogicFreeChecker | None = None,
    template_attribute_lister: FakeTemplateAttributeLister | None = None,
) -> ArgparseCommandLine:
    return ArgparseCommandLine(
        logic_free_checker=logic_free_checker or FakeLogicFreeChecker(),
        template_attribute_lister=template_attribute_lister or FakeTemplateAttributeLister(),
        cwd=_CWD,
    )


def test_logic_free_prints_each_problem_and_exits_1(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logic_free_checker = FakeLogicFreeChecker(
        "base.html:1: Or is not logic-free", "node.html:4: If is not logic-free"
    )
    command_line = _command_line(logic_free_checker=logic_free_checker)

    assert command_line.run(["logic-free", "templates"]) == 1

    assert capsys.readouterr().out == (
        "base.html:1: Or is not logic-free\nnode.html:4: If is not logic-free\n"
    )
    assert logic_free_checker.templates_directories == [Path("/work/templates")]


def test_logic_free_on_logic_free_templates_prints_nothing_and_exits_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _command_line().run(["logic-free", "templates"]) == 0

    assert capsys.readouterr().out == ""


def test_template_attributes_prints_the_attributes_sorted_and_comma_joined_and_exits_0(
    capsys: pytest.CaptureFixture[str],
) -> None:
    template_attribute_lister = FakeTemplateAttributeLister("size_mib", "filename")
    command_line = _command_line(template_attribute_lister=template_attribute_lister)

    assert command_line.run(["template-attributes", "templates"]) == 0

    assert capsys.readouterr().out == "filename,size_mib\n"
    assert template_attribute_lister.templates_directories == [Path("/work/templates")]


def test_an_absolute_templates_directory_is_taken_as_it_is() -> None:
    template_attribute_lister = FakeTemplateAttributeLister()
    command_line = _command_line(template_attribute_lister=template_attribute_lister)

    command_line.run(["template-attributes", "/srv/templates"])

    assert template_attribute_lister.templates_directories == [Path("/srv/templates")]


@pytest.mark.parametrize("command", ["logic-free", "template-attributes"])
def test_a_check_requires_the_templates_directory(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    logic_free_checker = FakeLogicFreeChecker()
    template_attribute_lister = FakeTemplateAttributeLister()

    with pytest.raises(SystemExit) as exit_info:
        _command_line(logic_free_checker, template_attribute_lister).run([command])

    assert exit_info.value.code == 2
    assert "the following arguments are required: templates_directory" in capsys.readouterr().err
    assert logic_free_checker.templates_directories == []
    assert template_attribute_lister.templates_directories == []


def test_the_bare_invocation_is_refused_with_a_usage_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _command_line().run([])

    assert exit_info.value.code == 2
    assert capsys.readouterr().err.startswith("usage: template_checks ")


def test_the_help_lists_the_subcommands(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _command_line().run(["--help"])

    assert exit_info.value.code == 0
    assert "{logic-free,template-attributes}" in capsys.readouterr().out
