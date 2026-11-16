"""Download tracking's health rules: the download disk under its floor, the client on no network."""

from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import Detections, HealthRule
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.work_components import BUGS

# As the disk alert always did: failing at the first reading under the floor, healthy at the first
# reading at or above it, so each dip alerts once.
DISK_SPACE_LOW = HealthRule(
    name="disk space low",
    fails_at=Detections(times=1, among_last=1),
    recovers_under=Detections(times=1, among_last=1),
)

# No channel of the client connected, so no download finds a source: 6 readings, as a channel's.
CONNECTED_TO_NO_NETWORK = HealthRule(
    name="connected to no network",
    fails_at=Detections(times=6, among_last=6),
    recovers_under=Detections(times=2, among_last=10),
)


def download_tracking_component(client_name: ClientName) -> Component:
    """Download tracking, judged by whether the download disk is under its floor, whether the client
    is connected to any network, and by its bugs: "download tracking amuled"."""
    return Component(
        name=f"download tracking {client_name}",
        client_name=client_name,
        rules=(DISK_SPACE_LOW, CONNECTED_TO_NO_NETWORK, BUGS),
    )
