import pytest

from p2pwatch.domain.health.external_dependency import (
    ExternalDependency,
    HealthAlert,
    HealthTransition,
)
from p2pwatch.domain.health.health_rule import Detections, HealthRule, HealthState
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.events import (
    ClientReachableAgain,
    ClientUnreachableLasting,
    Event,
)


def _rule(name: str) -> HealthRule:
    return HealthRule(
        name=name,
        fails_at=Detections(times=3, among_last=3),
        recovers_under=Detections(times=2, among_last=10),
    )


_UNREACHABLE = _rule("unreachable")
_NOT_CONNECTED = _rule("not connected")
_NODE_ID = NodeId("titar-node-1")
_UNREACHABLE_ALERT = HealthAlert(
    when_failing=ClientUnreachableLasting(
        client_name=ClientName("amuled"), unreachable_for_seconds=120.0, node_id=_NODE_ID
    ),
    when_healthy_again=ClientReachableAgain(client_name=ClientName("amuled"), node_id=_NODE_ID),
)


def _amule() -> ExternalDependency:
    return ExternalDependency(
        name="client amuled",
        client_name=ClientName("amuled"),
        rules={_UNREACHABLE: _UNREACHABLE_ALERT, _NOT_CONNECTED: None},
    )


def test_the_third_detection_in_a_row_returns_the_change_to_failing() -> None:
    amule = _amule()
    assert amule.record(rule=_UNREACHABLE, detected=True) is None
    assert amule.record(rule=_UNREACHABLE, detected=True) is None
    assert amule.record(rule=_UNREACHABLE, detected=True) == HealthTransition(
        alert=_UNREACHABLE_ALERT, previous=HealthState.UNKNOWN, current=HealthState.FAILING
    )


def test_a_fourth_detection_changes_nothing() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record(rule=_UNREACHABLE, detected=True)
    assert amule.record(rule=_UNREACHABLE, detected=True) is None


def test_3_checks_not_detected_return_the_change_to_healthy() -> None:
    amule = _amule()
    amule.record(rule=_UNREACHABLE, detected=False)
    amule.record(rule=_UNREACHABLE, detected=False)
    assert amule.record(rule=_UNREACHABLE, detected=False) == HealthTransition(
        alert=_UNREACHABLE_ALERT, previous=HealthState.UNKNOWN, current=HealthState.HEALTHY
    )


def test_a_change_under_a_rule_without_an_alert_carries_none() -> None:
    amule = _amule()
    *_, change = [amule.record(rule=_NOT_CONNECTED, detected=True) for _ in range(3)]
    assert change is not None
    assert change.alert is None


def test_a_check_counts_only_for_the_rule_it_is_recorded_for() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record(rule=_NOT_CONNECTED, detected=False)
    # "unreachable" has seen nothing yet: one check leaves it unknown.
    assert amule.record(rule=_UNREACHABLE, detected=False) is None


def _changes(checks: list[bool]) -> list[tuple[int, HealthState]]:
    """Each change of state under "unreachable", with the number of the check that caused it,
    counted from 1."""
    amule = _amule()
    transitions = [amule.record(rule=_UNREACHABLE, detected=detected) for detected in checks]
    return [(n, t.current) for n, t in enumerate(transitions, start=1) if t is not None]


def test_3_checks_not_detected_then_3_detected_over_and_over_fail_once_until_they_stop() -> None:
    pattern = ([False] * 3 + [True] * 3) * 20
    assert _changes(pattern + [False] * 10) == [
        (3, HealthState.HEALTHY),
        (6, HealthState.FAILING),  # the third detection
        (129, HealthState.HEALTHY),  # the ninth check not detected after the pattern stopped
    ]


def test_after_failing_it_turns_healthy_at_the_ninth_check_not_detected() -> None:
    # At the eighth, the rule still detected its case 2 times in the last 10 checks.
    assert _changes([True] * 3 + [False] * 9) == [
        (3, HealthState.FAILING),
        (12, HealthState.HEALTHY),
    ]


def _sent_at(
    *, previous: HealthState, current: HealthState, alert: HealthAlert | None = _UNREACHABLE_ALERT
) -> Event | None:
    """What the alert sends at a change from ``previous`` to ``current``."""
    return HealthTransition(alert=alert, previous=previous, current=current).alert_event()


@pytest.mark.parametrize("previous", [HealthState.UNKNOWN, HealthState.HEALTHY])
def test_a_rule_turning_failing_sends_its_alert(previous: HealthState) -> None:
    sent = _sent_at(previous=previous, current=HealthState.FAILING)
    assert sent == _UNREACHABLE_ALERT.when_failing


def test_a_rule_healthy_again_after_failing_sends_its_alert_s_end() -> None:
    sent = _sent_at(previous=HealthState.FAILING, current=HealthState.HEALTHY)
    assert sent == _UNREACHABLE_ALERT.when_healthy_again


def test_a_rule_healthy_from_its_first_checks_sends_nothing() -> None:
    assert _sent_at(previous=HealthState.UNKNOWN, current=HealthState.HEALTHY) is None


def test_an_alert_without_an_end_sends_nothing_once_healthy_again() -> None:
    no_end = HealthAlert(when_failing=_UNREACHABLE_ALERT.when_failing, when_healthy_again=None)
    sent = _sent_at(previous=HealthState.FAILING, current=HealthState.HEALTHY, alert=no_end)
    assert sent is None


@pytest.mark.parametrize(
    ("previous", "current"),
    [(HealthState.HEALTHY, HealthState.FAILING), (HealthState.FAILING, HealthState.HEALTHY)],
)
def test_a_rule_without_an_alert_sends_nothing(
    *, previous: HealthState, current: HealthState
) -> None:
    assert _sent_at(previous=previous, current=current, alert=None) is None
