import pytest

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import FailureThreshold, HealthCondition, HealthState

# Each attempt as the condition remembers it: whether it failed for the reason it counts.
_FAILED, _WORKED = True, False


class _Refused(DeclaredFailure):
    """The failure the condition under test counts."""


_REFUSED = HealthCondition(
    name="refused",
    counts=_Refused,
    fails_at=FailureThreshold(failures=3, among_last=3),
    recovers_under=FailureThreshold(failures=2, among_last=10),
)


def _states_after_each(attempts: list[bool]) -> list[HealthState]:
    """The condition's state after each of ``attempts``, in order."""
    latest_failed: tuple[bool, ...] = ()
    state = HealthState.UNKNOWN
    states = []
    for failed in attempts:
        latest_failed = (*latest_failed, failed)[-_REFUSED.attempts_kept :]
        state = _REFUSED.state_after(latest_failed, previous=state)
        states.append(state)
    return states


def _changes(attempts: list[bool]) -> list[tuple[int, HealthState]]:
    """Each change of state, with the number of the attempt that caused it, counted from 1."""
    states = [HealthState.UNKNOWN, *_states_after_each(attempts)]
    return [(n, states[n]) for n in range(1, len(states)) if states[n] is not states[n - 1]]


def test_the_state_is_unknown_until_the_third_attempt() -> None:
    assert _states_after_each([_WORKED] * 3) == [
        HealthState.UNKNOWN,
        HealthState.UNKNOWN,
        HealthState.HEALTHY,
    ]


def test_3_failures_in_a_row_from_the_start_make_it_failing() -> None:
    assert _states_after_each([_FAILED] * 3) == [
        HealthState.UNKNOWN,
        HealthState.UNKNOWN,
        HealthState.FAILING,
    ]


def test_after_failing_it_recovers_at_the_ninth_success() -> None:
    # At the eighth success, 2 of the last 10 attempts still failed.
    assert _changes([_FAILED] * 3 + [_WORKED] * 9) == [
        (3, HealthState.FAILING),
        (12, HealthState.HEALTHY),
    ]


def test_3_successes_then_3_failures_over_and_over_fail_once_and_recover_after_they_stop() -> None:
    pattern = ([_WORKED] * 3 + [_FAILED] * 3) * 20
    assert _changes(pattern + [_WORKED] * 9) == [
        (3, HealthState.HEALTHY),
        (6, HealthState.FAILING),
        (129, HealthState.HEALTHY),  # the ninth success after the pattern stopped
    ]


@pytest.mark.parametrize("failures", [0, 4])
def test_a_threshold_needs_from_1_failure_to_all_of_its_attempts(failures: int) -> None:
    with pytest.raises(ValueError, match="needs from 1 failure to all of its attempts"):
        FailureThreshold(failures=failures, among_last=3)


def test_a_condition_refuses_to_recover_under_more_failures_than_made_it_fail() -> None:
    with pytest.raises(ValueError, match="^'x' would recover on the failures that made it fail$"):
        HealthCondition(
            name="x",
            counts=_Refused,
            fails_at=FailureThreshold(failures=2, among_last=10),
            recovers_under=FailureThreshold(failures=3, among_last=10),
        )


def test_a_condition_refuses_to_recover_on_fewer_attempts_than_made_it_fail() -> None:
    with pytest.raises(ValueError, match="^'x' would recover on the failures that made it fail$"):
        HealthCondition(
            name="x",
            counts=_Refused,
            fails_at=FailureThreshold(failures=2, among_last=10),
            recovers_under=FailureThreshold(failures=2, among_last=2),
        )


def test_a_condition_may_fail_at_1_failure_and_recover_at_the_next_success() -> None:
    one_of_one = FailureThreshold(failures=1, among_last=1)
    condition = HealthCondition(
        name="disk", counts=_Refused, fails_at=one_of_one, recovers_under=one_of_one
    )
    assert condition.state_after((_WORKED,), previous=HealthState.FAILING) is HealthState.HEALTHY
