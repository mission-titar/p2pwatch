"""``DescribeHealth``: the objects left unrepaired among the alerts open."""

from p2pwatch.adapters.driven.in_memory_open_alert_store import InMemoryOpenAlertStore
from p2pwatch.application.use_cases.describe_health import DescribeHealth
from p2pwatch.domain.health.external_dependency import HealthAlert
from tests.support.domain.health_alerts import UNREACHABLE, UNREPAIRED


def _unrepaired_objects(*open_alerts: HealthAlert) -> tuple[str, ...]:
    open_alert_store = InMemoryOpenAlertStore()
    open_alert_store.set_open_alerts(open_alerts)
    return DescribeHealth(open_alert_store).describe_health().unrepaired_objects


def test_an_object_left_unrepaired_is_named_beside_an_outage() -> None:
    assert _unrepaired_objects(UNREACHABLE, UNREPAIRED) == ("client amuled",)


def test_an_outage_alone_leaves_no_object_unrepaired() -> None:
    assert _unrepaired_objects(UNREACHABLE) == ()
