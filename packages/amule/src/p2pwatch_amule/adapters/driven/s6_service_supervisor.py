from pathlib import Path

from p2pwatch_amule.ports.driven.service_supervisor import ServiceSupervisor


class S6ServiceSupervisor(ServiceSupervisor):
    """s6 over the services' directories: a ``down`` file keeps a service from starting."""

    def __init__(self, *, port_sync_service_directory: Path) -> None:
        self._port_sync_down_file = port_sync_service_directory / "down"

    def enable_port_sync(self) -> None:
        self._port_sync_down_file.unlink(missing_ok=True)

    def disable_port_sync(self) -> None:
        self._port_sync_down_file.touch()
