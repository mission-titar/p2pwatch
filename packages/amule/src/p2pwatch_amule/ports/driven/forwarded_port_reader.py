from abc import ABC, abstractmethod


class ForwardedPortReader(ABC):
    """Reads the port the VPN forwards to the container."""

    @abstractmethod
    def read_forwarded_port(self) -> int | None:
        """Returns the forwarded port, or None when none can be read; never raises."""
