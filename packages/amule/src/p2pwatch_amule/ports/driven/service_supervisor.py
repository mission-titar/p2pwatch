from abc import ABC, abstractmethod


class ServiceSupervisor(ABC):
    """Supervises the container's services: whether port-sync starts with the others."""

    @abstractmethod
    def enable_port_sync(self) -> None:
        """Lets port-sync start when the supervisor starts its services."""

    @abstractmethod
    def disable_port_sync(self) -> None:
        """Keeps port-sync down when the supervisor starts its services."""
