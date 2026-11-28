"""Alerts open as the tests set them: an outage's, and an object's left unrepaired."""

from datetime import UTC, datetime

from p2pwatch.domain.health.external_dependency import HealthAlert
from p2pwatch.domain.health.open_alert import OpenAlert
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.events import (
    ClientReachableAgain,
    ClientUnreachableLasting,
    WorksHealthyAgain,
    WorksStillFailing,
)

_NODE_ID = NodeId("n1")
UNREACHABLE = OpenAlert(
    alert=HealthAlert(
        about="client amuled, unreachable",
        when_failing=ClientUnreachableLasting(
            client_name=ClientName("amuled"), unreachable_for_seconds=120.0, node_id=_NODE_ID
        ),
        when_healthy_again=ClientReachableAgain(client_name=ClientName("amuled"), node_id=_NODE_ID),
    ),
    opened_at=datetime(2026, 6, 12, 14, 2, tzinfo=UTC),
)
UNREPAIRED = OpenAlert(
    alert=HealthAlert(
        about="client amuled",
        when_failing=WorksStillFailing(
            object_name="client amuled", works=("status reading",), rebuilds=3, node_id=_NODE_ID
        ),
        when_healthy_again=WorksHealthyAgain(object_name="client amuled", node_id=_NODE_ID),
    ),
    opened_at=datetime(2026, 6, 12, 14, 17, 30, tzinfo=UTC),
)
