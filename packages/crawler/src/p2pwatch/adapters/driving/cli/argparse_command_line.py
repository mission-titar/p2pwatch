"""The command line: parses a subcommand, calls its driving port, returns the exit code."""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import PurePath

from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.ports.driving.catalog_merger import (
    CatalogMerger,
    ListedSourceCatalog,
    MergeError,
    NewCatalog,
)
from p2pwatch.ports.driving.config_validator import ConfigValidator
from p2pwatch.ports.driving.crawler_runner import CrawlerRunner

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _add_config_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=PurePath, default=PurePath("deploy/crawler.yml"))
    parser.add_argument("--targets", type=PurePath, default=PurePath("deploy/targets.yml"))
    parser.add_argument("--matcher", type=PurePath, default=PurePath("deploy/matcher.yml"))


def _add_merge_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source_catalogs",
        metavar="CATALOG",
        nargs="+",
        type=PurePath,
        help="1..N catalog.db files to merge (≥ 1).",
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--output",
        "-o",
        type=PurePath,
        help="FRESH output file (refused if it exists, unless --force).",
    )
    destination.add_argument(
        "--into",
        type=PurePath,
        help="Destination = one of the listed source catalogs (merged into it).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow an existing --output (idempotent append, never truncate).",
    )


class ArgparseCommandLine:
    """``crawl``, ``validate-config`` and ``merge``, each over its driving port."""

    def __init__(
        self,
        *,
        crawler_runner: CrawlerRunner,
        config_validator: ConfigValidator,
        catalog_merger: CatalogMerger,
    ) -> None:
        self._crawler_runner = crawler_runner
        self._config_validator = config_validator
        self._catalog_merger = catalog_merger

    def run(self, argv: Sequence[str] | None = None) -> int:
        """Runs the subcommand ``argv`` names (``sys.argv`` if ``None``), returns its exit code."""
        logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
        parser = argparse.ArgumentParser(prog="p2pwatch", description="eMule crawler")
        subparsers = parser.add_subparsers(dest="command", required=True)
        _add_config_options(
            subparsers.add_parser("crawl", help="crawl the eMule network until stopped")
        )
        _add_config_options(
            subparsers.add_parser(
                "validate-config", help="load and check the config, start nothing"
            )
        )
        _add_merge_options(
            subparsers.add_parser(
                "merge",
                help="merge catalogs into one",
                description="Merge N catalog.db into one (idempotent, append-only preserved).",
            )
        )
        args = parser.parse_args(argv)
        if args.command == "crawl":
            return self._crawl(args)
        if args.command == "validate-config":
            return self._validate_config(args)
        return self._merge(args)

    def _crawl(self, args: argparse.Namespace) -> int:
        try:
            asyncio.run(
                self._crawler_runner.crawl(
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
            self._config_validator.validate_config(
                config_path=args.config, targets_path=args.targets, matcher_path=args.matcher
            )
        except InvalidConfigError as error:
            print(f"Invalid config: {error}", file=sys.stderr, flush=True)
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
        except MergeError as error:
            print(f"Merge failed: {error}", file=sys.stderr, flush=True)
            return 2
        return 0
