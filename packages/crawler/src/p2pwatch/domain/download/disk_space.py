"""The download disk's health rule: under its floor, no new download starts."""

from p2pwatch.domain.health.external_dependency import ExternalDependency, HealthAlert
from p2pwatch.domain.health.health_rule import Detections, HealthRule
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.observability.events import DiskSpaceLow, DiskSpaceSufficientAgain

# As the disk alert always did: failing at the first reading under the floor, healthy at the first
# reading at or above it, so each dip alerts once.
DISK_SPACE_LOW = HealthRule(
    name="disk space low",
    fails_at=Detections(times=1, among_last=1),
    recovers_under=Detections(times=1, among_last=1),
)


def download_disk_dependency(*, min_free_bytes: int, node_id: NodeId) -> ExternalDependency:
    """The download disk, judged by whether its free space is under the floor: "download
    disk"."""
    name = "download disk"
    alert = HealthAlert(
        about=f"{name}, {DISK_SPACE_LOW.name}",
        when_failing=DiskSpaceLow(min_free_bytes=min_free_bytes, node_id=node_id),
        when_healthy_again=DiskSpaceSufficientAgain(node_id=node_id),
    )
    return ExternalDependency(name=name, client_name=None, rules={DISK_SPACE_LOW: alert})
