import pytest

from p2pwatch.domain.health.health_rule import Detections, HealthRule, HealthState

# Each check as the rule remembers it: whether it detected its case.
_DETECTED, _NOT_DETECTED = True, False

_UNREACHABLE = HealthRule(
    name="unreachable",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)


def _state(*latest_detected: bool, previous: HealthState = HealthState.UNKNOWN) -> HealthState:
    return _UNREACHABLE.state_after(latest_detected, previous=previous)


def test_a_rule_keeps_as_many_checks_as_it_needs_to_turn_healthy() -> None:
    assert _UNREACHABLE.checks_kept == 10


def test_the_state_is_unknown_until_the_third_check() -> None:
    assert _state(_NOT_DETECTED, _NOT_DETECTED) is HealthState.UNKNOWN
    assert _state(_NOT_DETECTED, _NOT_DETECTED, _NOT_DETECTED) is HealthState.HEALTHY


def test_3_detections_in_a_row_make_it_failing() -> None:
    assert _state(_DETECTED, _DETECTED, _DETECTED) is HealthState.FAILING
    assert _state(_NOT_DETECTED, _DETECTED, _DETECTED) is HealthState.HEALTHY


def test_a_failing_rule_turns_healthy_under_2_detections_among_the_last_10() -> None:
    twice = (_DETECTED,) * 2 + (_NOT_DETECTED,) * 8
    once = (_DETECTED,) + (_NOT_DETECTED,) * 9
    assert _state(*twice, previous=HealthState.FAILING) is HealthState.FAILING
    assert _state(*once, previous=HealthState.FAILING) is HealthState.HEALTHY


@pytest.mark.parametrize("times", [0, 4])
def test_detections_count_from_1_to_all_of_their_checks(times: int) -> None:
    with pytest.raises(ValueError, match="needs from 1 detection to all of its checks"):
        Detections(times=times, among_last=3)


def test_a_rule_refuses_to_turn_healthy_under_more_detections_than_made_it_fail() -> None:
    with pytest.raises(
        ValueError, match="^'x' would turn healthy on the detections that made it fail$"
    ):
        HealthRule(
            name="x",
            fails_at=Detections(times=2, among_last=10),
            recovers_under=Detections(times=3, among_last=10),
        )


def test_a_rule_refuses_to_turn_healthy_on_fewer_checks_than_made_it_fail() -> None:
    with pytest.raises(
        ValueError, match="^'x' would turn healthy on the detections that made it fail$"
    ):
        HealthRule(
            name="x",
            fails_at=Detections(times=2, among_last=10),
            recovers_under=Detections(times=2, among_last=2),
        )


def test_a_rule_may_fail_at_1_detection_and_turn_healthy_at_the_next_check() -> None:
    one_of_one = Detections(times=1, among_last=1)
    rule = HealthRule(name="disk", fails_at=one_of_one, recovers_under=one_of_one)
    assert rule.state_after((_NOT_DETECTED,), previous=HealthState.FAILING) is HealthState.HEALTHY
