"""``PortSyncLoopRunner``: keeps amuled's listen port on gluetun's forwarded port, as amule."""

from abc import ABC, abstractmethod


class PortSyncLoopRunner(ABC):
    """Polls gluetun's forwarded port and sets amuled's ports to it live until the process stops."""

    @abstractmethod
    def run_port_sync_loop(self) -> None:
        """Never returns; raises ``SettingsError`` on a refused variable, ``ListenPortError`` when
        amuleapi fails other than not ready or rejecting the port."""
