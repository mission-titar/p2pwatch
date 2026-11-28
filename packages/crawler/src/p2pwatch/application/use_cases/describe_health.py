"""Describes the node's health from the alerts open: an object left unrepaired is the one state a
crawler restart may repair."""

from p2pwatch.application.ports.driven.open_alert_reader import OpenAlertReader
from p2pwatch.application.ports.driving.health_describer import HealthDescriber, HealthDescription
from p2pwatch.domain.observability.events import WorksStillFailing


class DescribeHealth(HealthDescriber):
    def __init__(self, open_alert_reader: OpenAlertReader) -> None:
        self._open_alert_reader = open_alert_reader

    def describe_health(self) -> HealthDescription:
        return HealthDescription(
            unrepaired_objects=tuple(
                open_alert.alert.when_failing.object_name
                for open_alert in self._open_alert_reader.read_open_alerts()
                if isinstance(open_alert.alert.when_failing, WorksStillFailing)
            )
        )
