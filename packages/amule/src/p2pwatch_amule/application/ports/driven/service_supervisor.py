from abc import ABC, abstractmethod


class ServiceSupervisor(ABC):
    """Supervises the container's services: whether port-sync starts with the others, amuled's
    stop and start."""

    @abstractmethod
    def enable_port_sync(self) -> None:
        """Lets port-sync start when the supervisor starts its services."""

    @abstractmethod
    def disable_port_sync(self) -> None:
        """Keeps port-sync down when the supervisor starts its services."""

    @abstractmethod
    def stop_amuled(self) -> bool:
        """Stops amuled and waits until it has exited; returns whether it has."""

    @abstractmethod
    def start_amuled(self) -> None:
        """Wants amuled up, whether it is down or already up."""
