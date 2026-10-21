"""The command line: parses a subcommand, calls its check, returns the exit code."""

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from template_checks.ports.driving.template_attribute_lister import TemplateAttributeLister


class ArgparseCommandLine:
    """``logic-free`` and ``template-attributes``, each over a templates directory. A relative
    path is taken under ``cwd``."""

    def __init__(
        self,
        *,
        check_logic_free: Callable[[Path], int],
        template_attribute_lister: TemplateAttributeLister,
        cwd: Path,
    ) -> None:
        self._check_logic_free = check_logic_free
        self._template_attribute_lister = template_attribute_lister
        self._cwd = cwd

    def run(self, argv: Sequence[str]) -> int:
        """Runs the subcommand ``argv`` names, returns its exit code."""
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
            subparser.add_argument(
                "templates_dir", type=self._under_cwd, help="the templates directory"
            )
        args = parser.parse_args(argv)
        if args.command == "logic-free":
            return self._check_logic_free(args.templates_dir)
        return self._list_template_attributes(args.templates_dir)

    def _list_template_attributes(self, templates_directory: Path) -> int:
        """Prints the attribute names the templates read, sorted and comma-joined."""
        template_attribute_listing = self._template_attribute_lister.list_template_attributes(
            templates_directory
        )
        print(",".join(sorted(template_attribute_listing.template_attributes)))
        return 0

    def _under_cwd(self, path: str) -> Path:
        """``path`` under ``cwd``, or as it is when absolute."""
        return self._cwd / path
