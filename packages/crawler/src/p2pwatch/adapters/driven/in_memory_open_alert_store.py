"""``InMemoryOpenAlertStore``: the alerts open, set by the node's health on the crawler's loop and
read on the webui's thread."""

from p2pwatch.application.ports.driven.open_alert_reader import OpenAlertReader
from p2pwatch.application.ports.driven.open_alert_writer import OpenAlertWriter
from p2pwatch.domain.health.open_alert import OpenAlert


class InMemoryOpenAlertStore(OpenAlertWriter, OpenAlertReader):
    def __init__(self) -> None:
        self._open_alerts: tuple[OpenAlert, ...] = ()

    def set_open_alerts(self, open_alerts: tuple[OpenAlert, ...]) -> None:
        # A tuple swapped whole, never mutated: the other thread reads it without a lock.
        self._open_alerts = open_alerts

    def read_open_alerts(self) -> tuple[OpenAlert, ...]:
        return self._open_alerts
