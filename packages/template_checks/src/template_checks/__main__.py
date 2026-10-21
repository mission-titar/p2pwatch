"""``python -m template_checks``: hands the checks to the command line."""

import functools
from collections.abc import Sequence

from template_checks.adapters.driven.filesystem_template_reader import FilesystemTemplateReader
from template_checks.adapters.driving import check_templates, read_names
from template_checks.adapters.driving.cli.argparse_command_line import ArgparseCommandLine


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the subcommand ``argv`` names (``sys.argv`` when ``None``), returns its exit code."""
    command_line = ArgparseCommandLine(
        check_logic_free=check_templates.main,
        print_read_names=functools.partial(
            read_names.main, template_reader=FilesystemTemplateReader()
        ),
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
