"""``PortSyncLoopRunner``: keeps amuled's listen port on gluetun's forwarded port, as amule."""

from abc import ABC, abstractmethod


class PortSyncLoopRunner(ABC):
    """Polls gluetun's forwarded port and restarts amuled on it, until the process is stopped."""

    @abstractmethod
    def run_port_sync_loop(self) -> None:
        """Never returns; raises ``SettingsError`` on a refused variable, ``OSError`` when the
        supervisor cannot be run."""
