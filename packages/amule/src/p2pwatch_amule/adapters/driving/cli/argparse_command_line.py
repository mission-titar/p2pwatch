"""The command line: parses a subcommand and runs its entry point."""

import argparse
import logging
from collections.abc import Callable, Sequence

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class ArgparseCommandLine:
    """``boot`` and ``port-sync``, each over its entry point, which reads its own variables."""

    def __init__(self, *, boot: Callable[[], None], sync_listen_port: Callable[[], None]) -> None:
        self._boot = boot
        self._sync_listen_port = sync_listen_port

    def run(self, argv: Sequence[str] | None = None) -> None:
        """Runs the subcommand ``argv`` names (``sys.argv`` if ``None``)."""
        logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT)
        parser = argparse.ArgumentParser(
            prog="p2pwatch_amule", description="aMule's container: boot step and port-sync"
        )
        subparsers = parser.add_subparsers(dest="command", required=True)
        subparsers.add_parser("boot", help="prepare the container, once, as root, before s6")
        subparsers.add_parser(
            "port-sync", help="keep amuled's listen port on gluetun's forwarded port"
        )
        args = parser.parse_args(argv)
        if args.command == "boot":
            self._boot()
        else:
            self._sync_listen_port()
