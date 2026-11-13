import pytest

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome, Threshold

U, H, F = Health.UNKNOWN, Health.HEALTHY, Health.FAILING
_THREE_OF_THREE = Threshold(failures=3, among_last=3)
_TWO_OF_TEN = Threshold(failures=2, among_last=10)


class _Refused(DeclaredFailure):
    """The failure the condition under test counts."""


_REFUSAL = _Refused("amuled refused the search")
_REFUSED = HealthCondition(
    name="refused", counts=_Refused, fails_at=_THREE_OF_THREE, recovers_under=_TWO_OF_TEN
)


def _healths(pattern: str, *, failure: DeclaredFailure = _REFUSAL) -> list[Health]:
    """The health after each outcome of ``pattern``: ``1`` a failure, ``0`` a success."""
    latest: tuple[Outcome, ...] = ()
    health, healths = U, []
    for mark in pattern:
        outcome = Outcome.failed(failure) if mark == "1" else Outcome.success()
        latest = (*latest, outcome)[-_REFUSED.outcomes_kept :]
        health = _REFUSED.health_after(latest, previous=health)
        healths.append(health)
    return healths


def test_an_outcome_is_a_success_or_the_failure_it_failed_with() -> None:
    assert (Outcome.success().reason, Outcome.failed(_REFUSAL).reason) == (None, _REFUSAL)


def test_a_condition_is_unknown_until_it_has_as_many_outcomes_as_its_failing_threshold() -> None:
    assert (_healths("000"), _healths("111")) == ([U, U, H], [U, U, F])


def test_a_repeating_pattern_fails_once_and_recovers_only_once_it_stops() -> None:
    healths = _healths("000111" * 20 + "0" * 10)
    assert healths[:5] == [U, U, H, H, H]
    assert healths[5:128] == [F] * 123  # the eighth success still sees two failures among ten
    assert healths[128:] == [H, H]


def test_a_failure_the_condition_does_not_count_is_a_success_for_it() -> None:
    assert _healths("111", failure=DeclaredFailure("another failure")) == [U, U, H]


@pytest.mark.parametrize("failures", [0, 4])
def test_a_threshold_counts_from_one_failure_to_all_of_its_outcomes(failures: int) -> None:
    with pytest.raises(
        ValueError, match=rf"^Threshold\(failures={failures}, among_last=3\): from 1"
    ):
        Threshold(failures=failures, among_last=3)


@pytest.mark.parametrize(
    "recovers_under", [Threshold(failures=3, among_last=10), Threshold(failures=2, among_last=2)]
)
def test_a_condition_refuses_to_recover_on_the_failures_that_made_it_fail(
    recovers_under: Threshold,
) -> None:
    with pytest.raises(ValueError, match="^'x' would recover on the failures that made it fail$"):
        HealthCondition(
            name="x", counts=_Refused, fails_at=_TWO_OF_TEN, recovers_under=recovers_under
        )


def test_a_condition_may_fail_at_one_failure_and_recover_at_the_next_success() -> None:
    once = Threshold(failures=1, among_last=1)
    condition = HealthCondition(name="once", counts=_Refused, fails_at=once, recovers_under=once)
    assert condition.health_after((Outcome.success(),), previous=F) is H
