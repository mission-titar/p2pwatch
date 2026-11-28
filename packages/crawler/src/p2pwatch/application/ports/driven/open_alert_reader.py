"""``OpenAlertReader``: reads the alerts open."""

from abc import ABC, abstractmethod

from p2pwatch.domain.health.open_alert import OpenAlert


class OpenAlertReader(ABC):
    """Reads the alerts open, from any thread."""

    @abstractmethod
    def read_open_alerts(self) -> tuple[OpenAlert, ...]:
        """The alerts last set, in their order; none before the first set."""
