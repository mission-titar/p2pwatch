from p2pwatch.domain.download.disk_space import DISK_SPACE_LOW, download_tracking_component
from p2pwatch.domain.health.health_rule import HealthState
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.work_components import BUGS


def _changes(*detected: bool) -> list[HealthState | None]:
    """Download tracking's new state under the disk's rule at each free-space reading, ``None``
    for a reading that changed nothing."""
    tracking = download_tracking_component(ClientName("amuled"))
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


def test_download_tracking_fails_at_the_third_bug_in_a_row_of_its_turns() -> None:
    tracking = download_tracking_component(ClientName("amuled"))
    transitions = [tracking.record(rule=BUGS, detected=True) for _ in range(3)]
    assert [t and t.current for t in transitions] == [None, None, HealthState.FAILING]
