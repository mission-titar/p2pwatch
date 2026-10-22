"""The command line of ``python -m template_checks``, on the checks."""

from pathlib import Path

from template_checks.adapters.driven.filesystem_template_reader import FilesystemTemplateReader
from template_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from template_checks.application.use_cases.check_logic_free import CheckLogicFree
from template_checks.application.use_cases.list_template_attributes import ListTemplateAttributes


def build_command_line(*, cwd: Path) -> ArgparseCommandLine:
    """The command line run in the directory ``cwd``."""
    template_reader = FilesystemTemplateReader()
    return ArgparseCommandLine(
        logic_free_checker=CheckLogicFree(template_reader=template_reader),
        template_attribute_lister=ListTemplateAttributes(template_reader=template_reader),
        cwd=cwd,
    )
