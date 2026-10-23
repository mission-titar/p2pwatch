"""The command line: one subcommand per check, over a templates directory taken under ``cwd``."""

from pathlib import PurePath

import pytest

from template_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from template_checks.domain.broken_input_error import BrokenInputError
from template_checks.domain.logic_constructs import FilteredLoop, RefusedNode
from tests.fakes.application.use_cases.fake_logic_free_checker import FakeLogicFreeChecker
from tests.fakes.application.use_cases.fake_template_attribute_lister import (
    FakeTemplateAttributeLister,
)

_CWD = PurePath("/work")


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
        RefusedNode(PurePath("base.html"), 1, "Or"), FilteredLoop(PurePath("pages/node.html"), 4)
    )
    command_line = _command_line(logic_free_checker=logic_free_checker)

    assert command_line.run(["logic-free", "templates"]) == 1

    assert capsys.readouterr().out == (
        "base.html:1: Or is not logic-free\n"
        "pages/node.html:4: For with an if filter is not logic-free\n"
    )
    assert logic_free_checker.templates_directories == [PurePath("/work/templates")]


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
    assert template_attribute_lister.templates_directories == [PurePath("/work/templates")]


@pytest.mark.parametrize("command", ["logic-free", "template-attributes"])
def test_a_broken_input_prints_its_error_on_one_line_and_exits_1(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    broken_input = BrokenInputError("page.html:2: Encountered unknown tag 'elif'.")
    command_line = _command_line(
        FakeLogicFreeChecker(broken_input=broken_input),
        FakeTemplateAttributeLister(broken_input=broken_input),
    )

    assert command_line.run([command, "templates"]) == 1

    assert capsys.readouterr() == ("", "error: page.html:2: Encountered unknown tag 'elif'.\n")


def test_an_absolute_templates_directory_is_taken_as_it_is() -> None:
    template_attribute_lister = FakeTemplateAttributeLister()
    command_line = _command_line(template_attribute_lister=template_attribute_lister)

    command_line.run(["template-attributes", "/srv/templates"])

    assert template_attribute_lister.templates_directories == [PurePath("/srv/templates")]


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
