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
from p2pwatch_amule.adapters.driven.system_monotonic_clock import SystemMonotonicClock
from p2pwatch_amule.adapters.driving.cli.argparse_command_line import ArgparseCommandLine
from p2pwatch_amule.composition.boot_composition import BootComposition
from p2pwatch_amule.composition.port_sync_composition import PortSyncComposition
from p2pwatch_amule.domain.conf import INCOMING_DIRECTORY, TEMP_DIRECTORY

_HOME_DIRECTORY = Path("/home/amule")
_CONFIG_DIRECTORY = _HOME_DIRECTORY / ".aMule"
_AMULE_CONF_PATH = _CONFIG_DIRECTORY / "amule.conf"
_PORT_SYNC_SERVICE_DIRECTORY = Path("/etc/services.d/port-sync")
_AMULED_SERVICE_DIRECTORY = Path("/etc/services.d/amuled")
_AMULED_STOP_TIMEOUT_SECONDS = 60


def build_command_line(
    *, env: Mapping[str, str], root_logger: logging.Logger
) -> ArgparseCommandLine:
    """The command line run in the environment ``env``, logging through ``root_logger``."""
    amule_conf_store = PosixAmuleConfStore(amule_conf_path=_AMULE_CONF_PATH, change_owner=os.chown)
    service_supervisor = S6ServiceSupervisor(
        port_sync_service_directory=_PORT_SYNC_SERVICE_DIRECTORY,
        amuled_service_directory=_AMULED_SERVICE_DIRECTORY,
        stop_timeout_seconds=_AMULED_STOP_TIMEOUT_SECONDS,
        run_command=subprocess.run,
    )
    return ArgparseCommandLine(
        container_booter=BootComposition(
            env=env,
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
            amule_conf_reader=amule_conf_store,
            amule_conf_writer=amule_conf_store,
            admin_password_setter=AmuleApiAdminPasswordSetter(
                config_directory=_CONFIG_DIRECTORY,
                home_directory=_HOME_DIRECTORY,
                env=env,
                run_command=subprocess.run,
            ),
            service_supervisor=service_supervisor,
        ),
        port_sync_loop_runner=PortSyncComposition(
            env=env,
            amule_conf_reader=amule_conf_store,
            amule_conf_writer=amule_conf_store,
            service_supervisor=service_supervisor,
            url_opener=build_opener(),  # gluetun reached through the environment's proxies, if any
            monotonic_clock=SystemMonotonicClock(),
        ),
        root_logger=root_logger,
    )
