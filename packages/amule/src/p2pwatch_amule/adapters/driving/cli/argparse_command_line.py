"""The command line: parses a subcommand and calls its driving port."""

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence

from p2pwatch_amule.domain.settings_error import SettingsError
from p2pwatch_amule.ports.driving.container_booter import ContainerBooter
from p2pwatch_amule.ports.driving.port_sync_loop_runner import PortSyncLoopRunner

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class ArgparseCommandLine:
    """``boot`` over ``container_booter`` in ``env``, ``port-sync`` over
    ``port_sync_loop_runner``; a refused variable is printed."""

    def __init__(
        self,
        *,
        container_booter: ContainerBooter,
        port_sync_loop_runner: PortSyncLoopRunner,
        env: Mapping[str, str],
        root_logger: logging.Logger,
    ) -> None:
        self._container_booter = container_booter
        self._port_sync_loop_runner = port_sync_loop_runner
        self._env = env
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
                self._container_booter.boot_container(self._env)
            else:
                self._port_sync_loop_runner.run_port_sync_loop()
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
