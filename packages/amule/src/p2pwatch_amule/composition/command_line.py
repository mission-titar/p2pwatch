"""The command line of ``python -m p2pwatch_amule``, on the driving ports' implementations."""

import grp
import logging
import os
import pwd
import subprocess
from collections.abc import Mapping
from pathlib import Path
from urllib.request import build_opener

from p2pwatch_amule.adapters.driven.amule_api_admin_password_setter import (
    AmuleApiAdminPasswordSetter,
)
from p2pwatch_amule.adapters.driven.posix_account_provisioner import PosixAccountProvisioner
from p2pwatch_amule.adapters.driven.posix_amule_conf_store import PosixAmuleConfStore
from p2pwatch_amule.adapters.driven.posix_amuled_directory_preparer import (
    PosixAmuledDirectoryPreparer,
)
from p2pwatch_amule.adapters.driven.s6_service_supervisor import S6ServiceSupervisor
from p2pwatch_amule.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch_amule.adapters.driven.system_monotonic_clock import SystemMonotonicClock
from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch_amule.application.use_cases.boot_container import BootContainer
from p2pwatch_amule.composition.port_sync_composition import PortSyncComposition
from p2pwatch_amule.domain.conf import INCOMING_DIRECTORY, TEMP_DIRECTORY

_HOME_DIRECTORY = Path("/home/amule")
_CONFIG_DIRECTORY = _HOME_DIRECTORY / ".aMule"
_AMULE_CONF_PATH = _CONFIG_DIRECTORY / "amule.conf"
_PORT_SYNC_SERVICE_DIRECTORY = Path("/etc/services.d/port-sync")
_AMULED_SERVICE_DIRECTORY = Path("/etc/services.d/amuled")


def build_command_line(
    *, env: Mapping[str, str], root_logger: logging.Logger
) -> ArgparseCommandLine:
    """The command line run in the environment ``env``, logging through ``root_logger``."""
    amule_conf = PosixAmuleConfStore(amule_conf_path=_AMULE_CONF_PATH, change_owner=os.chown)
    container_booter = BootContainer(
        account_provisioner=PosixAccountProvisioner(
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
                Path(INCOMING_DIRECTORY),
                Path(TEMP_DIRECTORY),
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
            port_sync_service_directory=_PORT_SYNC_SERVICE_DIRECTORY,
            amuled_service_directory=_AMULED_SERVICE_DIRECTORY,
            run_command=subprocess.run,
            logger=StdlibLogger("p2pwatch_amule.application.boot_container"),
        ),
    )
    return ArgparseCommandLine(
        container_booter=container_booter,
        port_sync_loop_runner=PortSyncComposition(
            env=env,
            amule_conf_path=_AMULE_CONF_PATH,
            port_sync_service_directory=_PORT_SYNC_SERVICE_DIRECTORY,
            amuled_service_directory=_AMULED_SERVICE_DIRECTORY,
            url_opener=build_opener(),  # gluetun reached through the environment's proxies, if any
            run_command=subprocess.run,
            change_owner=os.chown,
            monotonic_clock=SystemMonotonicClock(),
        ),
        env=env,
        root_logger=root_logger,
    )
