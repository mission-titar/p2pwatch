from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import FailureThreshold, HealthCondition, HealthState
from p2pwatch.domain.identifiers import ClientName


class _NoAnswer(DeclaredFailure):
    """The failure of the first condition."""


class _BadField(DeclaredFailure):
    """The failure of the second condition."""


def _condition(name: str, *, counts: type[DeclaredFailure]) -> HealthCondition:
    return HealthCondition(
        name=name,
        counts=counts,
        fails_at=FailureThreshold(failures=3, among_last=3),
        recovers_under=FailureThreshold(failures=2, among_last=10),
    )


_NOT_ANSWERING = _condition("not answering", counts=_NoAnswer)
_BAD_FIELD = _condition("bad field", counts=_BadField)


def _amule() -> Component:
    return Component(
        name="client amuled",
        client_name=ClientName("amuled"),
        conditions=(_NOT_ANSWERING, _BAD_FIELD),
    )


def test_the_third_failure_in_a_row_returns_the_change_to_failing() -> None:
    amule = _amule()
    assert amule.record_failure(_NoAnswer(), condition=_NOT_ANSWERING) is None
    assert amule.record_failure(_NoAnswer(), condition=_NOT_ANSWERING) is None
    assert amule.record_failure(_NoAnswer(), condition=_NOT_ANSWERING) == HealthTransition(
        component=amule,
        condition=_NOT_ANSWERING,
        previous=HealthState.UNKNOWN,
        current=HealthState.FAILING,
    )


def test_a_fourth_failure_changes_nothing() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record_failure(_NoAnswer(), condition=_NOT_ANSWERING)
    assert amule.record_failure(_NoAnswer(), condition=_NOT_ANSWERING) is None


def test_3_successes_return_the_change_to_healthy() -> None:
    amule = _amule()
    amule.record_success(condition=_NOT_ANSWERING)
    amule.record_success(condition=_NOT_ANSWERING)
    assert amule.record_success(condition=_NOT_ANSWERING) == HealthTransition(
        component=amule,
        condition=_NOT_ANSWERING,
        previous=HealthState.UNKNOWN,
        current=HealthState.HEALTHY,
    )


def test_a_failure_for_another_reason_counts_as_working() -> None:
    amule = _amule()
    for _ in range(2):
        amule.record_failure(_BadField(), condition=_NOT_ANSWERING)
    assert amule.record_failure(_BadField(), condition=_NOT_ANSWERING) == HealthTransition(
        component=amule,
        condition=_NOT_ANSWERING,
        previous=HealthState.UNKNOWN,
        current=HealthState.HEALTHY,
    )


def test_an_attempt_counts_only_for_the_condition_it_is_recorded_for() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record_success(condition=_BAD_FIELD)
    # "not answering" has seen nothing yet: one attempt leaves it unknown.
    assert amule.record_success(condition=_NOT_ANSWERING) is None
