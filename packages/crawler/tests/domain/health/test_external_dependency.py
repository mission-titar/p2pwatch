from p2pwatch.domain.health.external_dependency import (
    ExternalDependency,
    HealthAlert,
    HealthTransition,
)
from p2pwatch.domain.health.health_rule import Detections, HealthRule, HealthState
from p2pwatch.domain.identifiers import ClientName, NodeId
from p2pwatch.domain.observability.events import (
    ClientPasswordAcceptedAgain,
    ClientPasswordRefused,
    ClientReachableAgain,
    ClientUnreachableLasting,
)


def _rule(name: str) -> HealthRule:
    return HealthRule(
        name=name,
        fails_at=Detections(times=3, among_last=3),
        recovers_under=Detections(times=2, among_last=10),
    )


_UNREACHABLE = _rule("unreachable")
_PASSWORD_REFUSED = _rule("password refused")
_NODE_ID = NodeId("titar-node-1")
_AMULED = ClientName("amuled")
_UNREACHABLE_ALERT = HealthAlert(
    about="client amuled, unreachable",
    when_failing=ClientUnreachableLasting(
        client_name=_AMULED, unreachable_for_seconds=120.0, node_id=_NODE_ID
    ),
    when_healthy_again=ClientReachableAgain(client_name=_AMULED, node_id=_NODE_ID),
)
_PASSWORD_ALERT = HealthAlert(
    about="client amuled, password refused",
    when_failing=ClientPasswordRefused(client_name=_AMULED, node_id=_NODE_ID),
    when_healthy_again=ClientPasswordAcceptedAgain(client_name=_AMULED, node_id=_NODE_ID),
)


def _amule() -> ExternalDependency:
    return ExternalDependency(
        name="client amuled",
        client_name=_AMULED,
        rules={_UNREACHABLE: _UNREACHABLE_ALERT, _PASSWORD_REFUSED: _PASSWORD_ALERT},
    )


def test_the_type_refuses_a_rule_without_an_alert_and_an_alert_without_an_end() -> None:
    # mypy fails the gate on an unused ignore, the day the type accepts either again.
    ExternalDependency(name="client amuled", client_name=_AMULED, rules={_UNREACHABLE: None})  # type: ignore[dict-item]
    HealthAlert(about="", when_failing=_UNREACHABLE_ALERT.when_failing, when_healthy_again=None)  # type: ignore[arg-type]


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


def test_a_check_counts_only_for_the_rule_it_is_recorded_for() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record(rule=_PASSWORD_REFUSED, detected=False)
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
