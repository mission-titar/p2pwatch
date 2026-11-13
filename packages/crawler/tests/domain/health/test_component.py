from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome, Threshold
from p2pwatch.domain.identifiers import ClientName


class _NoAnswer(DeclaredFailure):
    """The failure of the first condition."""


class _BadField(DeclaredFailure):
    """The failure of the second condition."""


def _condition(name: str, *, counts: type[DeclaredFailure]) -> HealthCondition:
    return HealthCondition(
        name=name,
        counts=counts,
        fails_at=Threshold(failures=3, among_last=3),
        recovers_under=Threshold(failures=2, among_last=10),
    )


_NOT_ANSWERING = _condition("not answering", counts=_NoAnswer)
_BAD_FIELD = _condition("bad field", counts=_BadField)
_NO_ANSWER = Outcome.failed(_NoAnswer())
_WORKED = Outcome.success()


def _amule() -> Component:
    return Component(
        name="client amuled",
        client_name=ClientName("amuled"),
        conditions=(_NOT_ANSWERING, _BAD_FIELD),
    )


def test_the_third_failure_in_a_row_returns_the_change_to_failing() -> None:
    amule = _amule()
    assert amule.record(_NO_ANSWER, condition=_NOT_ANSWERING) is None
    assert amule.record(_NO_ANSWER, condition=_NOT_ANSWERING) is None
    assert amule.record(_NO_ANSWER, condition=_NOT_ANSWERING) == HealthTransition(
        component=amule,
        condition=_NOT_ANSWERING,
        previous=Health.UNKNOWN,
        current=Health.FAILING,
    )


def test_a_fourth_failure_changes_nothing() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record(_NO_ANSWER, condition=_NOT_ANSWERING)
    assert amule.record(_NO_ANSWER, condition=_NOT_ANSWERING) is None


def test_an_outcome_counts_only_for_the_condition_it_is_recorded_for() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record(_WORKED, condition=_BAD_FIELD)
    # "not answering" has seen nothing yet: one attempt leaves it unknown.
    assert amule.record(_WORKED, condition=_NOT_ANSWERING) is None
