from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import Detections, HealthRule, HealthState
from p2pwatch.domain.identifiers import ClientName


def _rule(name: str) -> HealthRule:
    return HealthRule(
        name=name,
        fails_at=Detections(times=3, among_last=3),
        recovers_under=Detections(times=2, among_last=10),
    )


_UNREACHABLE = _rule("unreachable")
_NOT_CONNECTED = _rule("not connected")


def _amule() -> Component:
    return Component(
        name="client amuled",
        client_name=ClientName("amuled"),
        rules=(_UNREACHABLE, _NOT_CONNECTED),
    )


def test_the_third_detection_in_a_row_returns_the_change_to_failing() -> None:
    amule = _amule()
    assert amule.record(rule=_UNREACHABLE, detected=True) is None
    assert amule.record(rule=_UNREACHABLE, detected=True) is None
    assert amule.record(rule=_UNREACHABLE, detected=True) == HealthTransition(
        component=amule,
        rule=_UNREACHABLE,
        previous=HealthState.UNKNOWN,
        current=HealthState.FAILING,
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
        component=amule,
        rule=_UNREACHABLE,
        previous=HealthState.UNKNOWN,
        current=HealthState.HEALTHY,
    )


def test_a_check_counts_only_for_the_rule_it_is_recorded_for() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record(rule=_NOT_CONNECTED, detected=False)
    # "unreachable" has seen nothing yet: one check leaves it unknown.
    assert amule.record(rule=_UNREACHABLE, detected=False) is None
