from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import HealthRule, HealthState
from p2pwatch.domain.observability.notification_sends import SENDS_FAILED, notifier_component
from p2pwatch.domain.work_components import BUGS


def _changes(rule: HealthRule, *detected: bool, on: Component) -> list[HealthState | None]:
    """The new state of ``on`` under ``rule`` at each check, ``None`` for a check that changed
    nothing."""
    transitions = [on.record(rule=rule, detected=each) for each in detected]
    return [None if transition is None else transition.current for transition in transitions]


def test_the_notifier_s_sends_fail_at_3_failed_in_a_row_and_heal_under_2_in_the_last_10() -> None:
    notifier = notifier_component()

    changes = _changes(SENDS_FAILED, *[True] * 3, *[False] * 9, on=notifier)

    # The ninth send that worked leaves a single failed send among the last 10.
    assert changes == [None, None, HealthState.FAILING, *[None] * 8, HealthState.HEALTHY]


def test_two_failed_sends_in_a_row_between_sends_that_worked_never_fail() -> None:
    notifier = notifier_component()

    changes = _changes(SENDS_FAILED, False, True, True, False, True, True, False, on=notifier)

    assert changes == [None, None, HealthState.HEALTHY, None, None, None, None]


def test_the_notifier_fails_at_the_third_bug_in_a_row_of_its_sends() -> None:
    notifier = notifier_component()

    changes = _changes(BUGS, True, True, True, on=notifier)

    assert changes == [None, None, HealthState.FAILING]


def test_the_notifier_s_part_is_named_notifier_and_by_no_client_or_channel() -> None:
    notifier = notifier_component()

    assert (notifier.name, notifier.client_name, notifier.channel) == ("notifier", None, None)
