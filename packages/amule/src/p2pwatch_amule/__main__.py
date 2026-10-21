"""``python -m p2pwatch_amule``: hands the entry points and their paths to the command line."""

import grp
import logging
import os
import pwd
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from p2pwatch_amule.adapters.driven.posix_account_manager import PosixAccountManager
from p2pwatch_amule.adapters.driving import boot, port_sync
from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch_amule.application.boot_container import BootContainer
from p2pwatch_amule.domain.conf import INCOMING_DIR, TEMP_DIR

_HOME_DIRECTORY = Path("/home/amule")
_CONFIG_DIRECTORY = _HOME_DIRECTORY / ".aMule"
_AMULE_CONF_PATH = _CONFIG_DIRECTORY / "amule.conf"
_PORT_SYNC_DOWN_FILE = Path("/etc/services.d/port-sync/down")
_AMULED_SERVICE_DIRECTORY = Path("/etc/services.d/amuled")


def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Runs the subcommand ``argv`` names in the environment ``env``, returns its exit code."""
    container_booter = BootContainer(
        account_manager=PosixAccountManager(
            home_directory=_HOME_DIRECTORY,
            run_command=subprocess.run,
            find_group=grp.getgrnam,
            find_user=pwd.getpwnam,
        )
    )
    command_line = ArgparseCommandLine(
        boot=lambda: boot.main(
            env,
            container_booter=container_booter,
            home_directory=_HOME_DIRECTORY,
            config_directory=_CONFIG_DIRECTORY,
            # The mount points are the directories reconcile_conf writes into amule.conf.
            incoming_directory=Path(INCOMING_DIR),
            temporary_directory=Path(TEMP_DIR),
            amule_conf_path=_AMULE_CONF_PATH,
            port_sync_down_file=_PORT_SYNC_DOWN_FILE,
        ),
        sync_listen_port=lambda: port_sync.main(
            env,
            amule_conf_path=_AMULE_CONF_PATH,
            amuled_service_directory=_AMULED_SERVICE_DIRECTORY,
        ),
        root_logger=logging.getLogger(),
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:], os.environ))
