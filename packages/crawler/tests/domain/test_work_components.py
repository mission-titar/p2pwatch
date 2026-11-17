from typing import Protocol

import pytest

from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword
from p2pwatch.domain.work_components import (
    BUGS,
    keyword_search_component,
    source_tracking_component,
    status_reading_component,
    webui_component,
)

_AMULED = ClientName("amuled")


def _changes(component: Component, *met_a_bug: bool) -> list[HealthState | None]:
    """The component's new state under the bugs rule at each turn, ``None`` for a turn that
    changed nothing."""
    transitions = [component.record(rule=BUGS, detected=bug) for bug in met_a_bug]
    return [None if transition is None else transition.current for transition in transitions]


def test_the_bugs_rule_fails_at_3_bugs_in_a_row_and_is_healthy_again_under_2_in_the_last_10() -> (
    None
):
    tracking = source_tracking_component(_AMULED)

    changes = _changes(tracking, *[True] * 3, *[False] * 9)

    # The ninth turn without a bug leaves a single bug among the last 10.
    assert changes == [None, None, HealthState.FAILING, *[None] * 8, HealthState.HEALTHY]


def test_two_bugs_in_a_row_between_turns_that_worked_never_fail() -> None:
    tracking = source_tracking_component(_AMULED)

    changes = _changes(tracking, False, True, True, False, True, True, False)

    assert changes == [None, None, HealthState.HEALTHY, None, None, None, None]


def test_a_keyword_search_s_part_is_named_as_its_search_on_its_client_s_channel() -> None:
    search = keyword_search_component(
        keyword=Keyword("keroro mission"), client_name=_AMULED, channel=Channel("kad")
    )

    assert (search.name, search.client_name, search.channel) == (
        "search 'keroro mission' amuled kad",
        "amuled",
        "kad",
    )


# Builds the part of one task of the client named ``client_name``.
class _PartOf(Protocol):
    def __call__(self, client_name: ClientName, /) -> Component: ...


def _kad_search_of_keroro(client_name: ClientName) -> Component:
    return keyword_search_component(
        keyword=Keyword("keroro"), client_name=client_name, channel=Channel("kad")
    )


@pytest.mark.parametrize(
    ("part_of", "name"),
    [
        (status_reading_component, "status reading amuled"),
        (source_tracking_component, "source tracking amuled"),
    ],
    ids=["status reading", "source tracking"],
)
def test_a_task_of_the_client_names_its_part_after_the_task_and_the_client(
    *, part_of: _PartOf, name: str
) -> None:
    component = part_of(_AMULED)
    assert (component.name, component.client_name, component.channel) == (name, "amuled", None)


@pytest.mark.parametrize(
    "part_of",
    [status_reading_component, _kad_search_of_keroro, source_tracking_component],
    ids=["status reading", "keyword search", "source tracking"],
)
def test_each_task_s_part_fails_at_its_third_bug_in_a_row(
    part_of: _PartOf,
) -> None:
    assert _changes(part_of(_AMULED), True, True, True) == [None, None, HealthState.FAILING]


def test_the_webui_s_part_is_named_webui_and_of_no_client() -> None:
    webui = webui_component()

    assert (webui.name, webui.client_name, webui.channel) == ("webui", None, None)


def test_the_webui_s_part_fails_at_its_third_bug_in_a_row() -> None:
    assert _changes(webui_component(), True, True, True) == [None, None, HealthState.FAILING]
