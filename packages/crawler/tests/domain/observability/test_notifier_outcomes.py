from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import TURNS, Outcome
from p2pwatch.domain.observability.notifier_outcomes import (
    NotificationRefused,
    NotificationTimedOut,
    notifier_component,
)


def test_a_refusal_and_a_timeout_are_declared_failures_apart() -> None:
    assert issubclass(NotificationRefused, DeclaredFailure)
    assert issubclass(NotificationTimedOut, DeclaredFailure)
    assert not issubclass(NotificationRefused, NotificationTimedOut)
    assert not issubclass(NotificationTimedOut, NotificationRefused)


def test_the_notifier_s_component_is_named_by_no_client_and_fails_on_three_bugs() -> None:
    component = notifier_component()
    transitions = [component.record(Outcome.bug("KeyError"), by=TURNS) for _ in range(3)]
    assert (component.name, component.labels) == ("notifier", ComponentLabels())
    assert [(t.condition.name, t.current) for t in transitions[2]] == [("bugs", Health.FAILING)]


def test_the_notifier_s_declared_failures_never_fail_its_bugs_condition() -> None:
    component = notifier_component()
    for failure in (NotificationRefused("403"), NotificationTimedOut("past 5 s")) * 2:
        component.record(Outcome.declared(failure), by=TURNS)
    assert component.health_of(BUGS) is Health.HEALTHY
