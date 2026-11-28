"""``OpenAlertReader``: reads the alerts open."""

from abc import ABC, abstractmethod

from p2pwatch.domain.health.external_dependency import HealthAlert


class OpenAlertReader(ABC):
    """Reads the alerts open, from any thread."""

    @abstractmethod
    def read_open_alerts(self) -> tuple[HealthAlert, ...]:
        """The alerts last set, in their order; none before the first set."""
