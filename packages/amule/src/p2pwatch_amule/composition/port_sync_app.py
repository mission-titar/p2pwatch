"""Port-sync's composition: parses its variables, then assembles and runs its loop."""

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.request import OpenerDirector

from p2pwatch_amule.adapters.driven.gluetun_forwarded_port_reader import (
    GluetunForwardedPortReader,
)
from p2pwatch_amule.adapters.driven.posix_amule_conf import PosixAmuleConf
from p2pwatch_amule.adapters.driven.s6_service_supervisor import S6ServiceSupervisor
from p2pwatch_amule.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch_amule.application.run_port_sync_loop import RunPortSyncLoop
from p2pwatch_amule.domain.settings import parse_port_sync_settings
from p2pwatch_amule.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.ports.driving.port_sync_loop_runner import PortSyncLoopRunner

_GLUETUN_TIMEOUT_SECONDS = 10


class PortSyncApp(PortSyncLoopRunner):
    """Parses port-sync's variables, then assembles and runs ``RunPortSyncLoop`` (composition
    root)."""

    def __init__(
        self,
        *,
        env: Mapping[str, str],
        amule_conf_path: Path,
        port_sync_service_directory: Path,
        amuled_service_directory: Path,
        url_opener: OpenerDirector,
        run_command: Callable[..., subprocess.CompletedProcess[str]],
        change_owner: Callable[[Path, int, int], None],
        monotonic_clock: MonotonicClock,
    ) -> None:
        self._env = env
        self._amule_conf_path = amule_conf_path
        self._port_sync_service_directory = port_sync_service_directory
        self._amuled_service_directory = amuled_service_directory
        self._url_opener = url_opener
        self._run_command = run_command
        self._change_owner = change_owner
        self._monotonic_clock = monotonic_clock

    def run_port_sync_loop(self) -> None:
        port_sync_settings = parse_port_sync_settings(self._env)
        # The two logger names docs/migration-4x.md gives the operator.
        logger = StdlibLogger("p2pwatch_amule.adapters.driving.port_sync")
        amule_conf = PosixAmuleConf(
            amule_conf_path=self._amule_conf_path, change_owner=self._change_owner
        )
        RunPortSyncLoop(
            port_sync_settings=port_sync_settings,
            forwarded_port_reader=GluetunForwardedPortReader(
                control_url=port_sync_settings.gluetun_control_url,
                timeout_seconds=_GLUETUN_TIMEOUT_SECONDS,
                logger=StdlibLogger("p2pwatch_amule.adapters.driven.gluetun"),
                url_opener=self._url_opener,
            ),
            amule_conf_reader=amule_conf,
            amule_conf_writer=amule_conf,
            service_supervisor=S6ServiceSupervisor(
                port_sync_service_directory=self._port_sync_service_directory,
                amuled_service_directory=self._amuled_service_directory,
                run_command=self._run_command,
                logger=logger,
            ),
            monotonic_clock=self._monotonic_clock,
            logger=logger,
        ).run_port_sync_loop()
