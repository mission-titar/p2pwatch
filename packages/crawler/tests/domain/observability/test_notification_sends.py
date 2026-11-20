from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
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


def _changes(rule: HealthRule, *detected: bool, on: ExternalDependency) -> list[HealthState | None]:
    """The new state of ``on`` under ``rule`` at each check, ``None`` for a check that changed
    nothing."""
    transitions = [on.record(rule=rule, detected=each) for each in detected]
    return [None if transition is None else transition.current for transition in transitions]


def _discord_part() -> ExternalDependency:
    return notification_service_dependencies([_DISCORD])[_DISCORD]


def test_a_service_is_named_by_its_scheme_and_its_audience_a_second_alike_by_its_ordinal() -> None:
    names = [str(service) for service in (_DISCORD, _SECOND_DISCORD, _NTFY)]

    assert names == ["discord community", "discord community 2", "ntfy operations"]


def test_each_service_has_a_part_of_its_own_named_after_it_and_by_no_client() -> None:
    parts = notification_service_dependencies([_DISCORD, _NTFY, _SECOND_DISCORD])

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
    part = local_database_dependency()

    changes = _changes(SAVES_FAILED, *[True] * 3, *[False] * 9, on=part)

    assert (part.name, part.client_name, part.channel) == ("local database", None, None)
    assert changes == [None, None, HealthState.FAILING, *[None] * 8, HealthState.HEALTHY]
