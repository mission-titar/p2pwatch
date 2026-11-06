from abc import ABC, abstractmethod


class ListenPortClient(ABC):
    """Changes amuled's listen ports through its API, amuled running on."""

    @abstractmethod
    def set_listen_port(self, port: int) -> None:
        """Sets amuled's TCP and UDP ports to ``port``; raises ``ApiNotReadyError`` while the API
        cannot serve, ``ListenPortRejectedError`` if amuled refuses it, or ``ListenPortError``."""
