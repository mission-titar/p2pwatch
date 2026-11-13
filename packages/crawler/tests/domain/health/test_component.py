from dataclasses import replace

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, HealthTransition
from p2pwatch.domain.health.health_condition import Health, HealthCondition, Outcome, Threshold
from p2pwatch.domain.identifiers import ClientName

_NOT_ANSWERING = HealthCondition(
    name="not answering",
    counts=DeclaredFailure,
    fails_at=Threshold(failures=3, among_last=3),
    recovers_under=Threshold(failures=2, among_last=10),
)
_BAD_FIELD = replace(_NOT_ANSWERING, name="bad field")
_FAILURE = Outcome.failed(DeclaredFailure("no answer"))
U, H, F = Health.UNKNOWN, Health.HEALTHY, Health.FAILING


def _component() -> Component:
    conditions = (_NOT_ANSWERING, _BAD_FIELD)
    return Component(name="client amuled", client_name=ClientName("amuled"), conditions=conditions)


def test_a_component_returns_a_transition_when_a_condition_changes_its_health() -> None:
    component = _component()
    failing = HealthTransition(component=component, condition=_NOT_ANSWERING, previous=U, current=F)
    records = [component.record(_FAILURE, condition=_NOT_ANSWERING) for _ in range(4)]
    assert records == [None, None, failing, None]  # still failing at the fourth: no change


def test_an_outcome_counts_only_for_the_condition_it_is_recorded_on() -> None:
    component = _component()
    for _ in range(3):
        component.record(_FAILURE, condition=_NOT_ANSWERING)
    transitions = [component.record(Outcome.success(), condition=_BAD_FIELD) for _ in range(3)]
    healthy = HealthTransition(component=component, condition=_BAD_FIELD, previous=U, current=H)
    assert transitions[2] == healthy  # three successes on the second condition, none on the first
    assert component.record(Outcome.success(), condition=_NOT_ANSWERING) is None
