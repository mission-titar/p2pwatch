"""``InMemoryOpenAlertStore``: the alerts open, set by the node's health on the crawler's loop and
read on the webui's thread."""

from p2pwatch.application.ports.driven.open_alert_reader import OpenAlertReader
from p2pwatch.application.ports.driven.open_alert_writer import OpenAlertWriter
from p2pwatch.domain.health.external_dependency import HealthAlert


class InMemoryOpenAlertStore(OpenAlertWriter, OpenAlertReader):
    def __init__(self) -> None:
        self._open_alerts: tuple[HealthAlert, ...] = ()

    def set_open_alerts(self, open_alerts: tuple[HealthAlert, ...]) -> None:
        # A tuple swapped whole, never mutated: the other thread reads it without a lock.
        self._open_alerts = open_alerts

    def read_open_alerts(self) -> tuple[HealthAlert, ...]:
        return self._open_alerts
