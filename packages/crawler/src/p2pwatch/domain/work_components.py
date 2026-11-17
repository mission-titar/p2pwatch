"""The bugs rule, and the parts of the node judged by it alone, one per task the node repeats."""

from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import Detections, HealthRule
from p2pwatch.domain.identifiers import Channel, ClientName, Keyword

# A bug is an exception nobody expected; one now and then fails its turn and nothing else.
BUGS = HealthRule(
    name="bugs",
    fails_at=Detections(times=3, among_last=3),
    recovers_under=Detections(times=2, among_last=10),
)


def status_reading_component(client_name: ClientName) -> Component:
    """The reading of the client's status, judged by its bugs: "status reading amuled"."""
    return Component(name=f"status reading {client_name}", client_name=client_name, rules=(BUGS,))


def keyword_search_component(
    *, keyword: Keyword, client_name: ClientName, channel: Channel
) -> Component:
    """One keyword's search on one channel, judged by its bugs: "search 'keroro' amuled kad"."""
    return Component(
        name=f"search '{keyword}' {client_name} {channel}",
        client_name=client_name,
        channel=channel,
        rules=(BUGS,),
    )


def source_tracking_component(client_name: ClientName) -> Component:
    """The tracking of the downloads' sources, judged by its bugs: "source tracking amuled"."""
    return Component(name=f"source tracking {client_name}", client_name=client_name, rules=(BUGS,))


def webui_component() -> Component:
    """The webui, judged by the bugs its thread watch finds: "webui"."""
    return Component(name="webui", client_name=None, rules=(BUGS,))
