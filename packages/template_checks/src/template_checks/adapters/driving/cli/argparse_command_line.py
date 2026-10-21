"""The command line: parses a subcommand, calls its check, returns the exit code."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path


class ArgparseCommandLine:
    """``logic-free`` and ``template-attributes``, each over a templates directory."""

    def __init__(
        self,
        *,
        check_logic_free: Callable[[Path], int],
        print_read_names: Callable[[Path], None],
    ) -> None:
        self._check_logic_free = check_logic_free
        self._print_read_names = print_read_names

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Runs the subcommand ``argv`` names (``sys.argv`` if ``None``), returns its exit code."""
        parser = argparse.ArgumentParser(
            prog="template_checks", description="keep the webui's Jinja templates logic-free"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        logic_free = subparsers.add_parser(
            "logic-free", help="fail on any logic tag or computed expression in a template"
        )
        template_attributes = subparsers.add_parser(
            "template-attributes", help="print the attribute names the templates read, comma-joined"
        )
        for subparser in (logic_free, template_attributes):
            subparser.add_argument("templates_dir", type=Path, help="the templates directory")
        args = parser.parse_args(argv)
        if args.command == "logic-free":
            return self._check_logic_free(args.templates_dir)
        self._print_read_names(args.templates_dir)
        return 0
