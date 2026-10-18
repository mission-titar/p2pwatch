"""The command line: parses a subcommand, calls its driving port, returns the exit code."""

import argparse
import asyncio
import logging
import sys
from collections.abc import Sequence
from pathlib import PurePath

from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.ports.driving.config_validator import ConfigValidator
from p2pwatch.ports.driving.crawler_runner import CrawlerRunner

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _add_config_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=PurePath, default=PurePath("deploy/crawler.yml"))
    parser.add_argument("--targets", type=PurePath, default=PurePath("deploy/targets.yml"))
    parser.add_argument("--matcher", type=PurePath, default=PurePath("deploy/matcher.yml"))


class ArgparseCommandLine:
    """``crawl`` and ``validate-config``, each over its driving port."""

    def __init__(self, *, crawler_runner: CrawlerRunner, config_validator: ConfigValidator) -> None:
        self._crawler_runner = crawler_runner
        self._config_validator = config_validator

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
        args = parser.parse_args(argv)
        if args.command == "crawl":
            return self._crawl(args)
        return self._validate_config(args)

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
