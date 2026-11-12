from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.component import ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS, Health
from p2pwatch.domain.health.outcome import UNITS_OF_WORK, Outcome
from p2pwatch.domain.observability.notifier_outcomes import (
    SENDS,
    SENDS_FAILED,
    NotificationRefused,
    NotificationService,
    NotificationTimedOut,
    notifier_components,
)
from p2pwatch.domain.observability.policy import Audience

_DISCORD = NotificationService(scheme="discord", audience=Audience.COMMUNITY)


def test_a_refusal_and_a_timeout_are_declared_failures_apart() -> None:
    assert issubclass(NotificationRefused, DeclaredFailure)
    assert issubclass(NotificationTimedOut, DeclaredFailure)
    assert not issubclass(NotificationRefused, NotificationTimedOut)
    assert not issubclass(NotificationTimedOut, NotificationRefused)


def test_a_service_is_named_by_its_scheme_and_its_audience_a_second_alike_by_its_ordinal() -> None:
    second = NotificationService(scheme="discord", audience=Audience.COMMUNITY, ordinal=2)
    assert [str(service) for service in (_DISCORD, second)] == [
        "discord community",
        "discord community 2",
    ]


def test_each_service_has_its_component_named_by_no_client() -> None:
    ntfy = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)
    components = notifier_components((_DISCORD, ntfy))
    assert [(service, c.name, c.labels) for service, c in components.items()] == [
        (_DISCORD, "notifier discord community", ComponentLabels()),
        (ntfy, "notifier ntfy operations", ComponentLabels()),
    ]


def test_a_service_s_component_fails_on_three_bugs() -> None:
    component = notifier_components((_DISCORD,))[_DISCORD]
    transitions = [component.record(Outcome.bug("KeyError"), by=UNITS_OF_WORK) for _ in range(3)]
    assert [(t.condition.name, t.current) for t in transitions[2]] == [("bugs", Health.FAILING)]


def test_a_service_s_declared_failures_never_fail_its_bugs_condition() -> None:
    component = notifier_components((_DISCORD,))[_DISCORD]
    for failure in (NotificationRefused("403"), NotificationTimedOut("past 5 s")) * 2:
        component.record(Outcome.declared(failure), by=UNITS_OF_WORK)
    assert component.health_of(BUGS) is Health.HEALTHY


def test_a_service_s_sends_refused_fails_on_three_refusals_its_sends_alone_counting() -> None:
    component = notifier_components((_DISCORD,))[_DISCORD]
    component.record(Outcome.declared(NotificationRefused("403")), by=UNITS_OF_WORK)
    assert component.health_of(SENDS_FAILED) is Health.UNKNOWN
    transitions = [
        component.record(Outcome.declared(NotificationRefused("403")), by=SENDS) for _ in range(3)
    ]
    assert [(t.condition.name, t.current) for t in transitions[2]] == [
        ("sends refused", Health.FAILING)
    ]


def test_a_timeout_is_no_refusal_for_sends_refused() -> None:
    component = notifier_components((_DISCORD,))[_DISCORD]
    for _ in range(3):
        component.record(Outcome.declared(NotificationTimedOut("past 5 s")), by=SENDS)
    assert component.health_of(SENDS_FAILED) is Health.HEALTHY
