"""The components only the works' turns feed, each judged on its bugs (spec v5 lot 4, D10)."""

from p2pwatch.domain.health.component import Component, ComponentLabels
from p2pwatch.domain.health.health_condition import BUGS
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword


def keyword_search_component(
    *, keyword: Keyword, client_name: ClientName, channel: Channel
) -> Component:
    return Component(
        name=f"search '{keyword}' {client_name} {channel}",
        labels=ComponentLabels(client_name=client_name, channel=channel),
        conditions=(BUGS,),
    )


def status_sensor_component(client_name: ClientName) -> Component:
    return _client_work_component("status sensor", client_name=client_name)


def download_tracking_component(client_name: ClientName) -> Component:
    return _client_work_component("download tracking", client_name=client_name)


def source_tracking_component(client_name: ClientName) -> Component:
    return _client_work_component("source tracking", client_name=client_name)


def _client_work_component(work: str, *, client_name: ClientName) -> Component:
    return Component(
        name=f"{work} {client_name}",
        labels=ComponentLabels(client_name=client_name),
        conditions=(BUGS,),
    )
