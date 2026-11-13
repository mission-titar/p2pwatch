import pytest

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome, Threshold


class _Refused(DeclaredFailure):
    """The failure the condition under test counts."""


_REFUSED = HealthCondition(
    name="refused",
    counts=_Refused,
    fails_at=Threshold(failures=3, among_last=3),
    recovers_under=Threshold(failures=2, among_last=10),
)
_WORKED = Outcome.success()
_FAILED = Outcome.failed(_Refused("amuled refused the search"))


def _health_after_each(outcomes: list[Outcome]) -> list[Health]:
    """The condition's health after each of ``outcomes``, in order."""
    latest: tuple[Outcome, ...] = ()
    health = Health.UNKNOWN
    healths = []
    for outcome in outcomes:
        latest = (*latest, outcome)[-_REFUSED.outcomes_kept :]
        health = _REFUSED.health_after(latest, previous=health)
        healths.append(health)
    return healths


def _changes(outcomes: list[Outcome]) -> list[tuple[int, Health]]:
    """Each change of health, with the number of the attempt that caused it, counted from 1."""
    healths = [Health.UNKNOWN, *_health_after_each(outcomes)]
    return [(n, healths[n]) for n in range(1, len(healths)) if healths[n] is not healths[n - 1]]


def test_an_outcome_either_worked_or_holds_the_failure_it_failed_with() -> None:
    refusal = _Refused("amuled refused the search")
    assert Outcome.success().reason is None
    assert Outcome.failed(refusal).reason is refusal


def test_the_health_is_unknown_until_the_third_attempt() -> None:
    assert _health_after_each([_WORKED] * 3) == [Health.UNKNOWN, Health.UNKNOWN, Health.HEALTHY]


def test_3_failures_in_a_row_from_the_start_make_it_failing() -> None:
    assert _health_after_each([_FAILED] * 3) == [Health.UNKNOWN, Health.UNKNOWN, Health.FAILING]


def test_after_failing_it_recovers_at_the_ninth_success() -> None:
    # At the eighth success, 2 of the last 10 attempts still failed.
    assert _changes([_FAILED] * 3 + [_WORKED] * 9) == [(3, Health.FAILING), (12, Health.HEALTHY)]


def test_3_successes_then_3_failures_over_and_over_fail_once_and_recover_after_they_stop() -> None:
    pattern = ([_WORKED] * 3 + [_FAILED] * 3) * 20
    assert _changes(pattern + [_WORKED] * 9) == [
        (3, Health.HEALTHY),
        (6, Health.FAILING),
        (129, Health.HEALTHY),  # the ninth success after the pattern stopped
    ]


def test_a_failure_the_condition_does_not_count_is_like_a_success() -> None:
    other = Outcome.failed(DeclaredFailure("another failure"))
    assert _health_after_each([other] * 3)[-1] is Health.HEALTHY


@pytest.mark.parametrize("failures", [0, 4])
def test_a_threshold_needs_from_1_failure_to_all_of_its_attempts(failures: int) -> None:
    with pytest.raises(ValueError, match="needs from 1 failure to all of its attempts"):
        Threshold(failures=failures, among_last=3)


def test_a_condition_refuses_to_recover_under_more_failures_than_made_it_fail() -> None:
    with pytest.raises(ValueError, match="^'x' would recover on the failures that made it fail$"):
        HealthCondition(
            name="x",
            counts=_Refused,
            fails_at=Threshold(failures=2, among_last=10),
            recovers_under=Threshold(failures=3, among_last=10),
        )


def test_a_condition_refuses_to_recover_on_fewer_attempts_than_made_it_fail() -> None:
    with pytest.raises(ValueError, match="^'x' would recover on the failures that made it fail$"):
        HealthCondition(
            name="x",
            counts=_Refused,
            fails_at=Threshold(failures=2, among_last=10),
            recovers_under=Threshold(failures=2, among_last=2),
        )


def test_a_condition_may_fail_at_1_failure_and_recover_at_the_next_success() -> None:
    one_of_one = Threshold(failures=1, among_last=1)
    condition = HealthCondition(
        name="disk", counts=_Refused, fails_at=one_of_one, recovers_under=one_of_one
    )
    assert condition.health_after((_WORKED,), previous=Health.FAILING) is Health.HEALTHY
