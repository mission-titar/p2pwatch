from p2pwatch.domain.download.disk_space import DISK_SPACE_LOW
from p2pwatch.domain.health.component import Component
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import ClientName


def _changes(*detected: bool) -> list[HealthState | None]:
    """Download tracking's new state under the disk's rule at each free-space reading, ``None``
    for a reading that changed nothing."""
    tracking = Component(
        name="download tracking amuled", client_name=ClientName("amuled"), rules=(DISK_SPACE_LOW,)
    )
    transitions = [tracking.record(rule=DISK_SPACE_LOW, detected=low) for low in detected]
    return [None if transition is None else transition.current for transition in transitions]


def test_the_disk_fails_at_its_first_low_reading_and_is_healthy_at_its_first_good_one() -> None:
    assert _changes(True, True, False, True) == [
        HealthState.FAILING,
        None,
        HealthState.HEALTHY,
        HealthState.FAILING,
    ]


def test_the_disk_good_at_its_first_reading_is_healthy() -> None:
    assert _changes(False) == [HealthState.HEALTHY]
