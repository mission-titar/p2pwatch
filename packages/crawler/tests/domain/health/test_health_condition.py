import pytest

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import (
    BUGS,
    AtLeast,
    Band,
    Below,
    ConditionWindow,
    Health,
    HealthCondition,
)
from p2pwatch.domain.health.outcome import TURNS, Outcome, OutcomeSource

U, H, D, F = Health.UNKNOWN, Health.HEALTHY, Health.DEGRADED, Health.FAILING


class _Refused(DeclaredFailure):
    """The reason the condition under test counts."""


class _Other(DeclaredFailure):
    """A reason of the same source the condition does not count."""


_CONDITION = HealthCondition(
    name="refused",
    source=OutcomeSource(name="a test's answers"),
    counting=_Refused,
    failing=Band(enters=AtLeast(count=3, of_last=3), leaves=Below(count=2, of_last=10)),
    degraded=None,
)
_DEGRADING = HealthCondition(
    name="refused",
    source=OutcomeSource(name="a test's answers"),
    counting=_Refused,
    failing=None,
    degraded=Band(enters=AtLeast(count=6, of_last=6), leaves=Below(count=1, of_last=20)),
)
_REFUSED = Outcome.declared(_Refused())
_BOTH_BANDS = HealthCondition(
    name="refused", source=OutcomeSource(name="a test's answers"), counting=_Refused
)


def _healths(
    pattern: str,
    *,
    condition: HealthCondition = _CONDITION,
    failure: Outcome = _REFUSED,
) -> list[Health]:
    """The health after each outcome, ``1`` a ``failure``, ``0`` a success."""
    window, healths = ConditionWindow(condition=condition), []
    for mark in pattern:
        window = window.after(failure if mark == "1" else Outcome.success())
        healths.append(window.health)
    return healths


def test_a_condition_is_unknown_until_its_window_holds_its_entry_s_outcomes() -> None:
    assert _healths("000") == [U, U, H]


def test_a_condition_enters_failing_at_its_entry_s_count_from_the_start() -> None:
    assert _healths("111") == [U, U, F]


def test_the_periodic_pattern_fails_at_its_third_failure_and_never_leaves_until_the_successes() -> (
    None
):
    healths = _healths("000111000111" * 10 + "0" * 10)
    assert healths[:5] == [U, U, H, H, H]
    assert healths[5:128] == [F] * 123  # the eighth success still sees two failures among ten
    assert healths[128:] == [H, H]


def test_a_degrading_condition_enters_degraded_and_leaves_it_under_its_own_exit() -> None:
    healths = _healths("1" * 6 + "0" * 20, condition=_DEGRADING)
    assert healths[:6] == [U] * 5 + [D]
    assert healths[6:] == [D] * 19 + [H]  # the 19th success still sees a failure among twenty


def test_the_periodic_pattern_under_both_bands_fails_at_its_third_failure_and_ends_healthy() -> (
    None
):
    healths = _healths("000111000111" * 10 + "0" * 10, condition=_BOTH_BANDS)
    assert healths[:6] == [U, U, H, H, D, F]
    assert healths[6:128] == [F] * 122
    # Leaving failing, degraded enters by its own entry alone: one failure among ten is not it.
    assert healths[128:] == [H, H]


def test_both_bands_enter_degraded_at_two_failures_among_ten_and_leave_it_after_twenty() -> None:
    healths = _healths("101" + "0" * 20, condition=_BOTH_BANDS)
    assert healths[:3] == [U, U, D]  # known at three outcomes, the smallest entry's window
    assert healths[3:] == [D] * 19 + [H]


def test_both_bands_enter_failing_from_degraded() -> None:
    assert _healths("10111", condition=_BOTH_BANDS) == [U, U, D, D, F]


def test_leaving_failing_enters_degraded_when_its_own_entry_holds() -> None:
    condition = HealthCondition(
        name="refused",
        source=_CONDITION.source,
        counting=_Refused,
        failing=Band(enters=AtLeast(count=3, of_last=3), leaves=Below(count=1, of_last=3)),
    )
    assert _healths("111000", condition=condition) == [U, U, F, F, F, D]


def test_a_condition_declaring_no_band_holds_the_default_bands() -> None:
    assert _BOTH_BANDS.failing == Band(
        enters=AtLeast(count=3, of_last=3), leaves=Below(count=2, of_last=10)
    )
    assert _BOTH_BANDS.degraded == Band(
        enters=AtLeast(count=2, of_last=10), leaves=Below(count=1, of_last=20)
    )


def test_a_condition_holds_a_band_at_least() -> None:
    with pytest.raises(ValueError, match="^the condition 'refused': a band at least expected"):
        HealthCondition(
            name="refused",
            source=_CONDITION.source,
            counting=_Refused,
            failing=None,
            degraded=None,
        )


def test_the_bugs_condition_counts_the_bugs_of_the_turns_under_both_bands() -> None:
    assert BUGS.source == TURNS
    assert (BUGS.failing, BUGS.degraded) == (_BOTH_BANDS.failing, _BOTH_BANDS.degraded)
    assert _healths("111", condition=BUGS, failure=Outcome.bug("KeyError")) == [U, U, F]
    assert _healths("111", condition=BUGS) == [U, U, H]  # a declared failure is no bug


def test_a_reason_the_condition_does_not_count_is_no_failure() -> None:
    window = ConditionWindow(condition=_CONDITION)
    for _ in range(3):
        window = window.after(Outcome.declared(_Other()))
    assert window.health is H


@pytest.mark.parametrize("bound", [AtLeast, Below])
@pytest.mark.parametrize(("count", "of_last"), [(0, 3), (4, 3)])
def test_a_bound_counts_between_one_and_its_window(
    *, bound: type[AtLeast | Below], count: int, of_last: int
) -> None:
    with pytest.raises(ValueError, match=f"^{count} among the last {of_last}: a count from 1"):
        bound(count=count, of_last=of_last)


@pytest.mark.parametrize(
    "leaves", [Below(count=4, of_last=10), Below(count=2, of_last=2)], ids=["count", "window"]
)
def test_a_band_s_exit_is_stricter_than_its_entry(leaves: Below) -> None:
    with pytest.raises(ValueError, match="^a band leaving below .* is not stricter than"):
        Band(enters=AtLeast(count=3, of_last=3), leaves=leaves)


def test_a_band_may_leave_at_its_first_good_reading_after_entering_at_one_of_one() -> None:
    band = Band(enters=AtLeast(count=1, of_last=1), leaves=Below(count=1, of_last=1))
    assert band.leaves.count == 1
