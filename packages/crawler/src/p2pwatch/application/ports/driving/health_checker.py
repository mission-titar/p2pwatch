"""``HealthChecker``: whether the node is healthy, as Docker's healthcheck reads it."""

from abc import ABC, abstractmethod


class HealthChecker(ABC):
    """Checks the node's health from outside its process."""

    @abstractmethod
    def check_health(self) -> bool:
        """True when the node's webui answers that no object is left unrepaired, else False;
        never raises."""
