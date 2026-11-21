"""The download disk's health rule: under its floor, no new download starts."""

from p2pwatch.domain.health.external_dependency import ExternalDependency
from p2pwatch.domain.health.health_rule import Detections, HealthRule

# As the disk alert always did: failing at the first reading under the floor, healthy at the first
# reading at or above it, so each dip alerts once.
DISK_SPACE_LOW = HealthRule(
    name="disk space low",
    fails_at=Detections(times=1, among_last=1),
    recovers_under=Detections(times=1, among_last=1),
)


def download_disk_dependency() -> ExternalDependency:
    """The download disk, judged by whether its free space is under the floor: "download
    disk"."""
    return ExternalDependency(name="download disk", client_name=None, rules=(DISK_SPACE_LOW,))
