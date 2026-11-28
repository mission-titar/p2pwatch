"""``OpenAlertWriter``: sets the alerts open."""

from abc import ABC, abstractmethod

from p2pwatch.domain.health.external_dependency import HealthAlert


class OpenAlertWriter(ABC):
    """Publishes the alerts open, from the node's health on the crawler's loop."""

    @abstractmethod
    def set_open_alerts(self, open_alerts: tuple[HealthAlert, ...]) -> None:
        """Replaces the alerts open, such as "client amuled" left unrepaired."""
