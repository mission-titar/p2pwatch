from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthAlert
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import (
    NotificationServiceSendsFailing,
    NotificationServiceSendsPassingAgain,
    NotificationsNotSaved,
    NotificationsSavedAgain,
)
from p2pwatch.domain.observability.notification_sends import (
    SAVES_FAILED,
    SENDS_FAILED,
    NotificationService,
    local_database_dependency,
    notification_service_dependencies,
)
from p2pwatch.domain.observability.policy import Audience

_DISCORD = NotificationService(scheme="discord", audience=Audience.COMMUNITY)
_SECOND_DISCORD = NotificationService(scheme="discord", audience=Audience.COMMUNITY, ordinal=2)
_NTFY = NotificationService(scheme="ntfy", audience=Audience.OPERATIONS)
_NODE_ID = NodeId("titar-node-1")


def _changes(rule: HealthRule, *detected: bool, on: ExternalDependency) -> list[HealthState | None]:
    """The new state of ``on`` under ``rule`` at each check, ``None`` for a check that changed
    nothing."""
    transitions = [on.record(rule=rule, detected=each) for each in detected]
    return [None if transition is None else transition.current for transition in transitions]


def _discord_part() -> ExternalDependency:
    return notification_service_dependencies([_DISCORD], node_id=_NODE_ID)[_DISCORD]


def test_a_service_is_named_by_its_scheme_and_its_audience_a_second_alike_by_its_ordinal() -> None:
    names = [str(service) for service in (_DISCORD, _SECOND_DISCORD, _NTFY)]

    assert names == ["discord community", "discord community 2", "ntfy operations"]


def test_each_service_has_a_part_of_its_own_named_after_it_and_by_no_client() -> None:
    parts = notification_service_dependencies([_DISCORD, _NTFY, _SECOND_DISCORD], node_id=_NODE_ID)

    named = [
        (service, part.name, part.client_name, part.channel) for service, part in parts.items()
    ]
    assert named == [
        (_DISCORD, "notifier discord community", None, None),
        (_NTFY, "notifier ntfy operations", None, None),
        (_SECOND_DISCORD, "notifier discord community 2", None, None),
    ]


def test_a_service_s_sends_fail_at_3_failed_in_a_row_and_heal_under_2_in_the_last_10() -> None:
    changes = _changes(SENDS_FAILED, *[True] * 3, *[False] * 9, on=_discord_part())

    # The ninth send that worked leaves a single failed send among the last 10.
    assert changes == [None, None, HealthState.FAILING, *[None] * 8, HealthState.HEALTHY]


def test_two_failed_sends_in_a_row_between_sends_that_worked_never_fail() -> None:
    changes = _changes(
        SENDS_FAILED, False, True, True, False, True, True, False, on=_discord_part()
    )

    assert changes == [None, None, HealthState.HEALTHY, None, None, None, None]


def test_the_local_database_s_saves_fail_at_3_failed_in_a_row_and_heal_under_2_in_the_last_10() -> (
    None
):
    part = local_database_dependency(node_id=_NODE_ID)

    changes = _changes(SAVES_FAILED, *[True] * 3, *[False] * 9, on=part)

    assert (part.name, part.client_name, part.channel) == ("local database", None, None)
    assert changes == [None, None, HealthState.FAILING, *[None] * 8, HealthState.HEALTHY]


def test_the_local_database_alerts_notifications_not_saved_and_ends_once_saved_again() -> None:
    part = local_database_dependency(node_id=_NODE_ID)
    *_, failing = [part.record(rule=SAVES_FAILED, detected=True) for _ in range(3)]
    assert failing is not None
    assert failing.alert == HealthAlert(
        about="local database, saves failed",
        when_failing=NotificationsNotSaved(node_id=_NODE_ID),
        when_healthy_again=NotificationsSavedAgain(node_id=_NODE_ID),
    )


def test_a_service_alerts_its_sends_failed_and_ends_once_they_pass_again() -> None:
    part = _discord_part()
    *_, failing = [part.record(rule=SENDS_FAILED, detected=True) for _ in range(3)]
    assert failing is not None
    assert failing.alert == HealthAlert(
        about="notifier discord community, sends failed",
        when_failing=NotificationServiceSendsFailing(
            service_name="discord community", node_id=_NODE_ID
        ),
        when_healthy_again=NotificationServiceSendsPassingAgain(
            service_name="discord community", node_id=_NODE_ID
        ),
    )
