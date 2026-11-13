"""The download disk's free space under its floor, judged at each reading as today's alert did:
entering at one low reading, leaving at the first good one (spec v5 lot 4, D9's mark)."""

from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.health.health_condition import AtLeast, Band, Below, HealthCondition
from p2pwatch.domain.health.outcome import OutcomeSource


class FreeSpaceBelowFloor(DeclaredFailure):
    """A free-space reading under the configured floor: a reason, never raised."""

    def __init__(self, *, free_bytes: int, min_free_bytes: int) -> None:
        super().__init__(f"{free_bytes} bytes free, under the {min_free_bytes} bytes floor")
        self.free_bytes = free_bytes
        self.min_free_bytes = min_free_bytes


FREE_SPACE_READING = OutcomeSource(name="the download disk's free-space reading")
DISK_SPACE_LOW = HealthCondition(
    name="disk space low",
    source=FREE_SPACE_READING,
    counting=FreeSpaceBelowFloor,
    failing=None,
    degraded=Band(enters=AtLeast(count=1, of_last=1), leaves=Below(count=1, of_last=1)),
)
