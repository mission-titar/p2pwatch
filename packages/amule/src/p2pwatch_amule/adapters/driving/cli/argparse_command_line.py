"""The command line: parses a subcommand and runs its entry point."""

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from p2pwatch_amule.domain.settings_error import SettingsError

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class ArgparseCommandLine:
    """``boot`` and ``port-sync``, each over its entry point; a refused variable is printed."""

    def __init__(
        self,
        *,
        boot: Callable[[], None],
        sync_listen_port: Callable[[], None],
        root_logger: logging.Logger,
    ) -> None:
        self._boot = boot
        self._sync_listen_port = sync_listen_port
        self._root_logger = root_logger

    def run(self, argv: Sequence[str]) -> int:
        """Runs the subcommand ``argv`` names, returns its exit code."""
        _configure_logging(self._root_logger)
        parser = argparse.ArgumentParser(
            prog="p2pwatch_amule", description="aMule's container: boot step and port-sync"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        subparsers.add_parser("boot", help="prepare the container, once, as root, before s6")
        subparsers.add_parser(
            "port-sync", help="keep amuled's listen port on gluetun's forwarded port"
        )
        args = parser.parse_args(argv)
        try:
            if args.command == "boot":
                self._boot()
            else:
                self._sync_listen_port()
        except SettingsError as error:
            print(error, file=sys.stderr)
            return 1
        return 0


def _configure_logging(root_logger: logging.Logger) -> None:
    """``logging.basicConfig`` on ``root_logger``: left as it is once it has a handler."""
    if root_logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
