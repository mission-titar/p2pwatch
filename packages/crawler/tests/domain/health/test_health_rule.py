import pytest

from p2pwatch.domain.health.health_rule import Detections, HealthRule, HealthState

# Each check as the rule remembers it: whether it detected its case.
_DETECTED, _NOT_DETECTED = True, False

_UNREACHABLE = HealthRule(
    name="unreachable",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)


def _states_after_each(checks: list[bool]) -> list[HealthState]:
    """The rule's state after each of ``checks``, in order."""
    latest_detected: tuple[bool, ...] = ()
    state = HealthState.UNKNOWN
    states = []
    for detected in checks:
        latest_detected = (*latest_detected, detected)[-_UNREACHABLE.checks_kept :]
        state = _UNREACHABLE.state_after(latest_detected, previous=state)
        states.append(state)
    return states


def _changes(checks: list[bool]) -> list[tuple[int, HealthState]]:
    """Each change of state, with the number of the check that caused it, counted from 1."""
    states = [HealthState.UNKNOWN, *_states_after_each(checks)]
    return [(n, states[n]) for n in range(1, len(states)) if states[n] is not states[n - 1]]


def test_the_state_is_unknown_until_the_third_check() -> None:
    assert _states_after_each([_NOT_DETECTED] * 3) == [
        HealthState.UNKNOWN,
        HealthState.UNKNOWN,
        HealthState.HEALTHY,
    ]


def test_3_detections_in_a_row_from_the_start_make_it_failing() -> None:
    assert _states_after_each([_DETECTED] * 3) == [
        HealthState.UNKNOWN,
        HealthState.UNKNOWN,
        HealthState.FAILING,
    ]


def test_after_failing_it_turns_healthy_at_the_ninth_check_not_detected() -> None:
    # At the eighth, the rule still detected its case 2 times in the last 10 checks.
    assert _changes([_DETECTED] * 3 + [_NOT_DETECTED] * 9) == [
        (3, HealthState.FAILING),
        (12, HealthState.HEALTHY),
    ]


def test_3_checks_not_detected_then_3_detected_over_and_over_fail_once_until_they_stop() -> None:
    pattern = ([_NOT_DETECTED] * 3 + [_DETECTED] * 3) * 20
    assert _changes(pattern + [_NOT_DETECTED] * 10) == [
        (3, HealthState.HEALTHY),
        (6, HealthState.FAILING),  # the third detection
        (129, HealthState.HEALTHY),  # the ninth check not detected after the pattern stopped
    ]


@pytest.mark.parametrize("times", [0, 4])
def test_detections_count_from_1_to_all_of_their_checks(times: int) -> None:
    with pytest.raises(ValueError, match="needs from 1 detection to all of its checks"):
        Detections(times=times, among_last=3)


def test_a_rule_refuses_to_turn_healthy_under_more_detections_than_made_it_fail() -> None:
    with pytest.raises(ValueError, match="^'x' would recover on the detections that made it fail$"):
        HealthRule(
            name="x",
            fails_at=Detections(times=2, among_last=10),
            recovers_under=Detections(times=3, among_last=10),
        )


def test_a_rule_refuses_to_turn_healthy_on_fewer_checks_than_made_it_fail() -> None:
    with pytest.raises(ValueError, match="^'x' would recover on the detections that made it fail$"):
        HealthRule(
            name="x",
            fails_at=Detections(times=2, among_last=10),
            recovers_under=Detections(times=2, among_last=2),
        )


def test_a_rule_may_fail_at_1_detection_and_turn_healthy_at_the_next_check() -> None:
    one_of_one = Detections(times=1, among_last=1)
    rule = HealthRule(name="disk", fails_at=one_of_one, recovers_under=one_of_one)
    assert rule.state_after((_NOT_DETECTED,), previous=HealthState.FAILING) is HealthState.HEALTHY
