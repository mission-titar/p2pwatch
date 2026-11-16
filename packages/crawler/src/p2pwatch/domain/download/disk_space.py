"""The download disk's health rule: under its floor at one reading, healthy at the next good one."""

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


def download_tracking_component(client_name: ClientName) -> Component:
    """Download tracking, judged by whether the download disk is under its floor and by its bugs:
    "download tracking amuled"."""
    return Component(
        name=f"download tracking {client_name}",
        client_name=client_name,
        rules=(DISK_SPACE_LOW, BUGS),
    )
