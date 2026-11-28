"""``OpenAlertWriter``: sets the alerts open."""

from abc import ABC, abstractmethod

from p2pwatch.domain.health.open_alert import OpenAlert


class OpenAlertWriter(ABC):
    """Publishes the alerts open, from the node's health on the crawler's loop."""

    @abstractmethod
    def set_open_alerts(self, open_alerts: tuple[OpenAlert, ...]) -> None:
        """Replaces the alerts open, such as "client amuled" left unrepaired."""
