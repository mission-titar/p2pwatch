from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import Health
from p2pwatch.domain.health.outcome import TURNS, Outcome
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword
from p2pwatch.domain.status_reading import STATUS_CONNECTED_CHANNELS, NoChannelConnected
from p2pwatch.domain.work_components import (
    download_tracking_component,
    keyword_search_component,
    source_tracking_component,
    status_sensor_component,
)

_AMULED = ClientName("amuled")


def _fails_on_three_bugs(component: Component) -> bool:
    transitions = [component.record(Outcome.bug("KeyError"), by=TURNS) for _ in range(3)]
    return [(t.condition.name, t.current) for t in transitions[2]] == [("bugs", Health.FAILING)]


def test_a_keyword_search_s_component_is_named_by_its_keyword_client_and_channel() -> None:
    component = keyword_search_component(
        keyword=Keyword("keroro mission"), client_name=_AMULED, channel=Channel("kad")
    )
    assert (component.name, component.labels) == (
        "search 'keroro mission' amuled kad",
        ComponentLabels(client_name=_AMULED, channel=Channel("kad")),
    )
    assert _fails_on_three_bugs(component)


def test_the_client_s_other_works_components_are_named_by_their_work_and_client() -> None:
    components = [
        status_sensor_component(_AMULED),
        download_tracking_component(_AMULED),
        source_tracking_component(_AMULED),
    ]
    assert [(c.name, c.labels) for c in components] == [
        (name, ComponentLabels(client_name=_AMULED))
        for name in ("status sensor amuled", "download tracking amuled", "source tracking amuled")
    ]
    assert all(_fails_on_three_bugs(component) for component in components)


def test_download_tracking_fails_on_three_readings_of_a_client_connected_to_no_network() -> None:
    component = download_tracking_component(_AMULED)
    transitions = [
        component.record(Outcome.declared(NoChannelConnected()), by=STATUS_CONNECTED_CHANNELS)
        for _ in range(3)
    ]
    assert [[(t.condition.name, t.current) for t in each] for each in transitions] == [
        [],
        [],
        [("connected to no network", Health.FAILING)],
    ]
