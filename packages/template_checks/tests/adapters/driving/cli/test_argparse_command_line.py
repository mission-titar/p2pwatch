"""The command line: one subcommand per check, over a templates directory taken under ``cwd``."""

from pathlib import Path, PurePath

import pytest

from template_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from template_checks.ports.driving.template_attribute_lister import (
    TemplateAttributeLister,
    TemplateAttributeListing,
)

_CWD = Path("/work")


class FakeTemplateAttributeLister(TemplateAttributeLister):
    """Lists the attributes it is given, recording each directory it is asked for."""

    def __init__(self, *template_attributes: str) -> None:
        self._template_attributes = frozenset(template_attributes)
        self.templates_directories: list[PurePath] = []

    def list_template_attributes(self, templates_directory: PurePath) -> TemplateAttributeListing:
        self.templates_directories.append(templates_directory)
        return TemplateAttributeListing(template_attributes=self._template_attributes)


class _LogicFreeCheck:
    """Records each templates directory it checks."""

    def __init__(self) -> None:
        self.templates_directories: list[Path] = []

    def __call__(self, templates_dir: Path) -> int:
        self.templates_directories.append(templates_dir)
        return 3


def _command_line(
    logic_free_check: _LogicFreeCheck | None = None,
    template_attribute_lister: FakeTemplateAttributeLister | None = None,
) -> ArgparseCommandLine:
    return ArgparseCommandLine(
        check_logic_free=logic_free_check or _LogicFreeCheck(),
        template_attribute_lister=template_attribute_lister or FakeTemplateAttributeLister(),
        cwd=_CWD,
    )


def test_logic_free_runs_its_check_over_the_directory_and_returns_its_exit_code() -> None:
    logic_free_check = _LogicFreeCheck()

    assert _command_line(logic_free_check=logic_free_check).run(["logic-free", "templates"]) == 3

    assert logic_free_check.templates_directories == [Path("/work/templates")]


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
    logic_free_check = _LogicFreeCheck()
    template_attribute_lister = FakeTemplateAttributeLister()

    with pytest.raises(SystemExit) as exit_info:
        _command_line(logic_free_check, template_attribute_lister).run([command])

    assert exit_info.value.code == 2
    assert "the following arguments are required: templates_dir" in capsys.readouterr().err
    assert logic_free_check.templates_directories == []
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
