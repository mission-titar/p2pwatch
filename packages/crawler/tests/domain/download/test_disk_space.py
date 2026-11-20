from p2pwatch.domain.download.disk_space import DISK_SPACE_LOW, download_disk_dependency
from p2pwatch.domain.health.health_rule import HealthState


def _changes(*detected: bool) -> list[HealthState | None]:
    """The download disk's new state at each free-space reading, ``None`` for a reading that
    changed nothing."""
    disk = download_disk_dependency()
    transitions = [disk.record(rule=DISK_SPACE_LOW, detected=low) for low in detected]
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


def test_the_download_disk_is_named_after_it_and_by_no_client() -> None:
    disk = download_disk_dependency()
    assert (disk.name, disk.client_name, disk.channel) == ("download disk", None, None)
