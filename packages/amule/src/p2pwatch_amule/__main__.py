"""``python -m p2pwatch_amule``: wires the driving port and the entry point to the command line."""

import grp
import logging
import os
import pwd
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from p2pwatch_amule.adapters.driven.amule_api_admin_password_setter import (
    AmuleApiAdminPasswordSetter,
)
from p2pwatch_amule.adapters.driven.posix_account_manager import PosixAccountManager
from p2pwatch_amule.adapters.driven.posix_amule_conf import PosixAmuleConf
from p2pwatch_amule.adapters.driven.posix_amuled_directory_preparer import (
    PosixAmuledDirectoryPreparer,
)
from p2pwatch_amule.adapters.driven.s6_service_supervisor import S6ServiceSupervisor
from p2pwatch_amule.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch_amule.adapters.driven.system_monotonic_clock import SystemMonotonicClock
from p2pwatch_amule.adapters.driving import port_sync
from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch_amule.application.boot_container import BootContainer
from p2pwatch_amule.domain.conf import INCOMING_DIR, TEMP_DIR

_HOME_DIRECTORY = Path("/home/amule")
_CONFIG_DIRECTORY = _HOME_DIRECTORY / ".aMule"
_AMULE_CONF_PATH = _CONFIG_DIRECTORY / "amule.conf"
_PORT_SYNC_SERVICE_DIRECTORY = Path("/etc/services.d/port-sync")
_AMULED_SERVICE_DIRECTORY = Path("/etc/services.d/amuled")


def main(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Runs the subcommand ``argv`` names in the environment ``env``, returns its exit code."""
    amule_conf = PosixAmuleConf(amule_conf_path=_AMULE_CONF_PATH, change_owner=os.chown)
    container_booter = BootContainer(
        account_manager=PosixAccountManager(
            home_directory=_HOME_DIRECTORY,
            run_command=subprocess.run,
            find_group=grp.getgrnam,
            find_user=pwd.getpwnam,
        ),
        amuled_directory_preparer=PosixAmuledDirectoryPreparer(
            # The mount points are the directories reconcile_conf writes into amule.conf.
            owned_directories=[
                _HOME_DIRECTORY,
                _CONFIG_DIRECTORY,
                Path(INCOMING_DIR),
                Path(TEMP_DIR),
            ],
            change_owner=os.chown,
        ),
        amule_conf_reader=amule_conf,
        amule_conf_writer=amule_conf,
        admin_password_setter=AmuleApiAdminPasswordSetter(
            config_directory=_CONFIG_DIRECTORY,
            home_directory=_HOME_DIRECTORY,
            env=env,
            run_command=subprocess.run,
        ),
        service_supervisor=S6ServiceSupervisor(
            port_sync_service_directory=_PORT_SYNC_SERVICE_DIRECTORY
        ),
    )
    command_line = ArgparseCommandLine(
        container_booter=container_booter,
        sync_listen_port=lambda: port_sync.main(
            env,
            amule_conf_path=_AMULE_CONF_PATH,
            amuled_service_directory=_AMULED_SERVICE_DIRECTORY,
            monotonic_clock=SystemMonotonicClock(),
            # The two names docs/migration-4x.md gives the operator.
            logger=StdlibLogger("p2pwatch_amule.adapters.driving.port_sync"),
            gluetun_logger=StdlibLogger("p2pwatch_amule.adapters.driven.gluetun"),
        ),
        env=env,
        root_logger=logging.getLogger(),
    )
    return command_line.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:], os.environ))
