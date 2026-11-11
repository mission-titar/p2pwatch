from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import Component, ComponentLabels, HealthTransition
from p2pwatch.domain.health.health_condition import AtLeast, Band, Below, Health, HealthCondition
from p2pwatch.domain.health.outcome import Outcome, OutcomeSource
from p2pwatch.domain.identifiers import ClientName

_ANSWERS = OutcomeSource(name="the answers")
_FIELDS = OutcomeSource(name="the fields")
_BAND = Band(enters=AtLeast(count=3, of_last=3), leaves=Below(count=2, of_last=10))


class _NoAnswer(DeclaredFailure):
    """The answers' reason."""


class _BadField(DeclaredFailure):
    """The fields' reason."""


_NOT_ANSWERING = HealthCondition(
    name="not answering", source=_ANSWERS, counting=_NoAnswer, failing=_BAND, degraded=None
)
_BAD_FIELD = HealthCondition(
    name="bad field", source=_FIELDS, counting=_BadField, failing=_BAND, degraded=None
)


def _component() -> Component:
    return Component(
        name="client amuled",
        labels=ComponentLabels(client_name=ClientName("amuled")),
        conditions=(_NOT_ANSWERING, _BAD_FIELD),
    )


def test_a_component_gives_a_transition_when_one_of_its_conditions_changes() -> None:
    component = _component()
    failure = Outcome.declared(_NoAnswer())
    assert component.record(failure, by=_ANSWERS) == ()
    assert component.record(failure, by=_ANSWERS) == ()
    assert component.record(failure, by=_ANSWERS) == (
        HealthTransition(
            component=component,
            condition=_NOT_ANSWERING,
            previous=Health.UNKNOWN,
            current=Health.FAILING,
        ),
    )
    assert component.record(failure, by=_ANSWERS) == ()  # still failing: no change


def test_an_outcome_feeds_only_the_conditions_of_its_source() -> None:
    component = _component()
    for _ in range(3):
        component.record(Outcome.declared(_NoAnswer()), by=_ANSWERS)
    transitions = [component.record(Outcome.success(), by=_FIELDS) for _ in range(3)]
    assert transitions[:2] == [(), ()]
    assert [(t.condition, t.previous, t.current) for t in transitions[2]] == [
        (_BAD_FIELD, Health.UNKNOWN, Health.HEALTHY)
    ]  # three successes of the fields counted nothing toward the answers' failures


def test_an_outcome_of_a_source_no_condition_reads_changes_nothing() -> None:
    component = _component()
    assert [
        component.record(Outcome.success(), by=OutcomeSource(name="the turns")) for _ in range(3)
    ] == [(), (), ()]


def test_a_component_holds_its_name_and_labels() -> None:
    component = _component()
    assert (component.name, component.labels.client_name) == ("client amuled", "amuled")
