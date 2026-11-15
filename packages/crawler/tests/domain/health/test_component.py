from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_rule import FailureThreshold, HealthRule, HealthState
from p2pwatch.domain.identifiers import ClientName


def _rule(name: str, *, counts: type[Exception]) -> HealthRule:
    return HealthRule(
        name=name,
        counts=counts,
        fails_at=FailureThreshold(failures=3, among_last=3),
        recovers_under=FailureThreshold(failures=2, among_last=10),
    )


_NOT_ANSWERING = _rule("not answering", counts=TimeoutError)
_BAD_FIELD = _rule("bad field", counts=ValueError)


def _amule() -> Component:
    return Component(
        name="client amuled",
        client_name=ClientName("amuled"),
        rules=(_NOT_ANSWERING, _BAD_FIELD),
    )


def test_the_third_failure_in_a_row_returns_the_change_to_failing() -> None:
    amule = _amule()
    assert amule.record_failure(TimeoutError(), rule=_NOT_ANSWERING) is None
    assert amule.record_failure(TimeoutError(), rule=_NOT_ANSWERING) is None
    assert amule.record_failure(TimeoutError(), rule=_NOT_ANSWERING) == HealthTransition(
        component=amule,
        rule=_NOT_ANSWERING,
        previous=HealthState.UNKNOWN,
        current=HealthState.FAILING,
    )


def test_a_fourth_failure_changes_nothing() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record_failure(TimeoutError(), rule=_NOT_ANSWERING)
    assert amule.record_failure(TimeoutError(), rule=_NOT_ANSWERING) is None


def test_3_successes_return_the_change_to_healthy() -> None:
    amule = _amule()
    amule.record_success(rule=_NOT_ANSWERING)
    amule.record_success(rule=_NOT_ANSWERING)
    assert amule.record_success(rule=_NOT_ANSWERING) == HealthTransition(
        component=amule,
        rule=_NOT_ANSWERING,
        previous=HealthState.UNKNOWN,
        current=HealthState.HEALTHY,
    )


def test_a_failure_with_another_error_counts_as_working() -> None:
    amule = _amule()
    for _ in range(2):
        amule.record_failure(ValueError(), rule=_NOT_ANSWERING)
    assert amule.record_failure(ValueError(), rule=_NOT_ANSWERING) == HealthTransition(
        component=amule,
        rule=_NOT_ANSWERING,
        previous=HealthState.UNKNOWN,
        current=HealthState.HEALTHY,
    )


def test_an_attempt_counts_only_for_the_rule_it_is_recorded_for() -> None:
    amule = _amule()
    for _ in range(3):
        amule.record_success(rule=_BAD_FIELD)
    # "not answering" has seen nothing yet: one attempt leaves it unknown.
    assert amule.record_success(rule=_NOT_ANSWERING) is None
