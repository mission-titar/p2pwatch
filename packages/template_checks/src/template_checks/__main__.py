"""``python -m template_checks``: hands the checks to the command line."""

import sys
from collections.abc import Sequence
from pathlib import Path

from template_checks.adapters.driven.filesystem_template_reader import FilesystemTemplateReader
from template_checks.adapters.driving import check_templates
from template_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from template_checks.application.list_template_attributes import ListTemplateAttributes


def main(argv: Sequence[str], cwd: Path) -> int:
    """Runs the subcommand ``argv`` names in the directory ``cwd``, returns its exit code."""
    command_line = ArgparseCommandLine(
        check_logic_free=check_templates.main,
        template_attribute_lister=ListTemplateAttributes(
            template_reader=FilesystemTemplateReader()
        ),
        cwd=cwd,
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:], Path.cwd()))
