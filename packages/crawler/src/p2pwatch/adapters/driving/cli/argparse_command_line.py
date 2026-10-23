"""The command line: parses a subcommand, calls its driving port, returns the exit code."""

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import PurePath

from p2pwatch.application.ports.driving.catalog_merger import (
    CatalogMerger,
    ListedSourceCatalog,
    NewCatalog,
)
from p2pwatch.application.ports.driving.config_validator import ConfigProblem, ConfigValidator
from p2pwatch.application.ports.driving.crawler_runner import CrawlerRunner
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.config_defaults import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_MATCHER_PATH,
    DEFAULT_TARGETS_PATH,
)
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.merge_error import MergeError, OutputIsSourceError

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _add_config_options(
    parser: argparse.ArgumentParser, under_cwd: Callable[[str | PurePath], PurePath]
) -> None:
    parser.add_argument("--config", type=under_cwd, default=under_cwd(DEFAULT_CONFIG_PATH))
    parser.add_argument("--targets", type=under_cwd, default=under_cwd(DEFAULT_TARGETS_PATH))
    parser.add_argument("--matcher", type=under_cwd, default=under_cwd(DEFAULT_MATCHER_PATH))


def _configure_logging(root_logger: logging.Logger) -> None:
    """``logging.basicConfig`` on ``root_logger``: left as it is once it has a handler."""
    if root_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def _add_merge_options(
    parser: argparse.ArgumentParser, under_cwd: Callable[[str], PurePath]
) -> None:
    parser.add_argument(
        "source_catalogs",
        metavar="CATALOG",
        nargs="+",
        type=under_cwd,
        help="1..N catalog.db files to merge (≥ 1).",
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--output",
        "-o",
        type=under_cwd,
        help="FRESH output file (refused if it exists, unless --force).",
    )
    destination.add_argument(
        "--into",
        type=under_cwd,
        help="Destination = one of the listed source catalogs (merged into it).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow an existing --output (idempotent append, never truncate).",
    )


def _problem_line(problem: ConfigProblem) -> str:
    """``<file>: <key>: <message>``, or ``<file>: <message>`` for a problem naming no key."""
    if problem.key is None:
        return f"{problem.file_path}: {problem.message}"
    return f"{problem.file_path}: {problem.key}: {problem.message}"


class ArgparseCommandLine:
    """``crawl``, ``validate-config`` and ``merge``, each over its driving port; a relative path,
    the config's default ones included, is taken under ``cwd``."""

    def __init__(
        self,
        *,
        crawler_runner: CrawlerRunner,
        config_validator: ConfigValidator,
        catalog_merger: CatalogMerger,
        root_logger: logging.Logger,
        cwd: PurePath,
    ) -> None:
        self._crawler_runner = crawler_runner
        self._config_validator = config_validator
        self._catalog_merger = catalog_merger
        self._root_logger = root_logger
        self._cwd = cwd

    def run(self, argv: Sequence[str]) -> int:
        """Runs the subcommand ``argv`` names, returns its exit code."""
        _configure_logging(self._root_logger)
        parser = argparse.ArgumentParser(prog="p2pwatch", description="eMule crawler")
        subparsers = parser.add_subparsers(dest="command", required=True)
        _add_config_options(
            subparsers.add_parser("crawl", help="crawl the eMule network until stopped"),
            self._under_cwd,
        )
        _add_config_options(
            subparsers.add_parser(
                "validate-config", help="load and check the config, start nothing"
            ),
            self._under_cwd,
        )
        _add_merge_options(
            subparsers.add_parser(
                "merge",
                help="merge catalogs into one",
                description="Merge N catalog.db into one (idempotent, append-only preserved).",
            ),
            self._under_cwd,
        )
        args = parser.parse_args(argv)
        if args.command == "crawl":
            return self._crawl(args)
        if args.command == "validate-config":
            return self._validate_config(args)
        return self._merge(args)

    def _under_cwd(self, path: str | PurePath) -> PurePath:
        """``path`` under ``cwd``, or as it is when absolute."""
        return self._cwd / path

    def _crawl(self, args: argparse.Namespace) -> int:
        try:
            asyncio.run(
                self._crawler_runner.run_crawler(
                    config_path=args.config, targets_path=args.targets, matcher_path=args.matcher
                )
            )
        except InvalidConfigError as error:
            print(f"Invalid config, refusing to start: {error}", file=sys.stderr, flush=True)
            return 1
        except TimeoutError:
            # The deadline firing is the crawler keeping its promise not to hang; a worker timing
            # out escapes as an ``ExceptionGroup`` instead, and exits non-zero like any crash.
            print(
                "Shutdown deadline elapsed: exiting on the bound rather than hanging.",
                file=sys.stderr,
                flush=True,
            )
        return 0

    def _validate_config(self, args: argparse.Namespace) -> int:
        try:
            config_report = self._config_validator.validate_config(
                config_path=args.config, targets_path=args.targets, matcher_path=args.matcher
            )
        except BrokenInputError as error:
            print(f"error: {error}", file=sys.stderr, flush=True)
            return 1
        for problem in config_report.problems:
            print(f"Invalid config: {_problem_line(problem)}", file=sys.stderr, flush=True)
        if config_report.problems:
            return 1
        print("Config valid", flush=True)
        return 0

    def _merge(self, args: argparse.Namespace) -> int:
        destination: NewCatalog | ListedSourceCatalog
        if args.into is None:
            destination = NewCatalog(args.output, force=args.force)
        elif args.force:
            print("Merge failed: --force makes no sense with --into", file=sys.stderr, flush=True)
            return 2
        else:
            destination = ListedSourceCatalog(args.into)
        try:
            self._catalog_merger.merge_catalogs(args.source_catalogs, destination)
        except OutputIsSourceError as error:
            print(
                f"Merge failed: output is one of the source catalogs: {error.output}"
                " (merge into it with --into)",
                file=sys.stderr,
                flush=True,
            )
            return 2
        except MergeError as error:
            print(f"Merge failed: {error}", file=sys.stderr, flush=True)
            return 2
        return 0
