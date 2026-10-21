"""``python -m p2pwatch_amule``: wires the driving port and the entry point to the command line."""

import grp
import logging
import os
import pwd
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from urllib.request import OpenerDirector, build_opener

from p2pwatch_amule.adapters.driven.amule_api_admin_password_setter import (
    AmuleApiAdminPasswordSetter,
)
from p2pwatch_amule.adapters.driven.gluetun_forwarded_port_reader import (
    GluetunForwardedPortReader,
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
from p2pwatch_amule.domain.settings import parse_port_sync_settings

_HOME_DIRECTORY = Path("/home/amule")
_CONFIG_DIRECTORY = _HOME_DIRECTORY / ".aMule"
_AMULE_CONF_PATH = _CONFIG_DIRECTORY / "amule.conf"
_PORT_SYNC_SERVICE_DIRECTORY = Path("/etc/services.d/port-sync")
_AMULED_SERVICE_DIRECTORY = Path("/etc/services.d/amuled")
_GLUETUN_TIMEOUT_SECONDS = 10


def main(
    argv: Sequence[str],
    env: Mapping[str, str],
    url_opener: OpenerDirector,
    run_port_sync: Callable[..., None],
) -> int:
    """Runs the subcommand ``argv`` names in the environment ``env``, gluetun read by
    ``url_opener``, port-sync's loop by ``run_port_sync``; returns its exit code."""
    amule_conf = PosixAmuleConf(amule_conf_path=_AMULE_CONF_PATH, change_owner=os.chown)
    # The two logger names docs/migration-4x.md gives the operator, here and for gluetun's reader.
    port_sync_logger = StdlibLogger("p2pwatch_amule.adapters.driving.port_sync")
    service_supervisor = S6ServiceSupervisor(
        port_sync_service_directory=_PORT_SYNC_SERVICE_DIRECTORY,
        amuled_service_directory=_AMULED_SERVICE_DIRECTORY,
        run_command=subprocess.run,
        logger=port_sync_logger,
    )
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
        service_supervisor=service_supervisor,
    )
    command_line = ArgparseCommandLine(
        container_booter=container_booter,
        sync_listen_port=lambda: _sync_listen_port(
            env,
            url_opener,
            run_port_sync,
            amule_conf=amule_conf,
            service_supervisor=service_supervisor,
            logger=port_sync_logger,
        ),
        env=env,
        root_logger=logging.getLogger(),
    )
    return command_line.run(argv)


def _sync_listen_port(
    env: Mapping[str, str],
    url_opener: OpenerDirector,
    run_port_sync: Callable[..., None],
    *,
    amule_conf: PosixAmuleConf,
    service_supervisor: S6ServiceSupervisor,
    logger: StdlibLogger,
) -> None:
    """Parses port-sync's variables, so that the command line prints a refused one, then runs it."""
    port_sync_settings = parse_port_sync_settings(env)
    run_port_sync(
        port_sync_settings,
        forwarded_port_reader=GluetunForwardedPortReader(
            control_url=port_sync_settings.gluetun_control_url,
            timeout_seconds=_GLUETUN_TIMEOUT_SECONDS,
            logger=StdlibLogger("p2pwatch_amule.adapters.driven.gluetun"),
            url_opener=url_opener,
        ),
        amule_conf_reader=amule_conf,
        amule_conf_writer=amule_conf,
        service_supervisor=service_supervisor,
        monotonic_clock=SystemMonotonicClock(),
        logger=logger,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(
        main(
            sys.argv[1:],
            os.environ,
            build_opener(),  # the environment's proxies, as urlopen followed them
            port_sync.main,
        )
    )
