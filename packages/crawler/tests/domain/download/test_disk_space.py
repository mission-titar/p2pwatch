from p2pwatch.domain.declared_failure import DeclaredFailure
from p2pwatch.domain.download.disk_space import (
    DISK_SPACE_LOW,
    FREE_SPACE_READING,
    FreeSpaceBelowFloor,
)
from p2pwatch.domain.health.health_condition import ConditionWindow, Health
from p2pwatch.domain.health.outcome import Outcome

_LOW = Outcome.declared(FreeSpaceBelowFloor(free_bytes=500, min_free_bytes=600))
_GOOD = Outcome.success()


def _healths(*outcomes: Outcome) -> list[Health]:
    window, healths = ConditionWindow(condition=DISK_SPACE_LOW), []
    for outcome in outcomes:
        window = window.after(outcome)
        healths.append(window.health)
    return healths


def test_a_reading_below_the_floor_carries_its_figures() -> None:
    reason = FreeSpaceBelowFloor(free_bytes=500, min_free_bytes=600)
    assert isinstance(reason, DeclaredFailure)
    assert (reason.free_bytes, reason.min_free_bytes) == (500, 600)
    assert str(reason) == "500 bytes free, under the 600 bytes floor"


def test_the_disk_condition_reads_the_free_space_degraded_alone() -> None:
    assert DISK_SPACE_LOW.source == FREE_SPACE_READING
    assert [health for health, _ in DISK_SPACE_LOW.bands()] == [Health.DEGRADED]


def test_the_disk_condition_enters_at_one_low_reading_and_leaves_at_the_first_good_one() -> None:
    # Today's edge: a second dip after one good reading alerts again.
    assert _healths(_LOW, _LOW, _GOOD, _LOW) == [
        Health.DEGRADED,
        Health.DEGRADED,
        Health.HEALTHY,
        Health.DEGRADED,
    ]
    assert _healths(_GOOD) == [Health.HEALTHY]
