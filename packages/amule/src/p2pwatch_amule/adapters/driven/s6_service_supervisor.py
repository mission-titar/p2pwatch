import subprocess
from collections.abc import Callable
from pathlib import Path

from p2pwatch_amule.application.ports.driven.logger import Logger
from p2pwatch_amule.application.ports.driven.service_supervisor import ServiceSupervisor


class S6ServiceSupervisor(ServiceSupervisor):
    """s6 over the services' directories: a ``down`` file keeps a service from starting,
    ``s6-svc``, run through ``run_command``, stops and starts amuled."""

    def __init__(
        self,
        *,
        port_sync_service_directory: Path,
        amuled_service_directory: Path,
        run_command: Callable[..., subprocess.CompletedProcess[str]],
        logger: Logger,
    ) -> None:
        self._port_sync_down_file = port_sync_service_directory / "down"
        self._amuled_service_directory = amuled_service_directory
        self._run_command = run_command
        self._logger = logger

    def enable_port_sync(self) -> None:
        self._port_sync_down_file.unlink(missing_ok=True)

    def disable_port_sync(self) -> None:
        self._port_sync_down_file.touch()

    def stop_amuled(self) -> bool:
        return self._signal_amuled("-wD", "-T", "60000", "-d")

    def start_amuled(self) -> None:
        self._signal_amuled("-u")

    def _signal_amuled(self, *options: str) -> bool:
        """Run `s6-svc <options>` on amuled; return whether it exited 0, logging why not."""
        result = self._run_command(
            ["s6-svc", *options, str(self._amuled_service_directory)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            command, stderr = " ".join(["s6-svc", *options]), result.stderr.strip()
            self._logger.error("%s exited %d: %s", command, result.returncode, stderr)
        return result.returncode == 0
