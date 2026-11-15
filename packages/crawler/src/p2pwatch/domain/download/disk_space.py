"""The download disk's free space, read before each round of download decisions."""

from p2pwatch.domain.health.health_rule import Detections, HealthRule

# As the disk alert always did: failing at the first reading under the floor, healthy at the first
# reading at or above it, so each dip alerts once.
DISK_SPACE_LOW = HealthRule(
    name="disk space low",
    fails_at=Detections(times=1, among_last=1),
    recovers_under=Detections(times=1, among_last=1),
)
