"""Port-sync's decision: amuled restarts on a new port, at most once per restart window."""

from datetime import timedelta

from p2pwatch_amule.domain.amuled_restart import is_amuled_restart_due
from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant

RESTART_MIN_INTERVAL = timedelta(seconds=300)


def instant_at(seconds: int) -> MonotonicInstant:
    return MonotonicInstant(seconds * 1_000_000_000)


def is_due(
    forwarded_port: int, latest_restart: MonotonicInstant | None, now: MonotonicInstant
) -> bool:
    return is_amuled_restart_due(
        forwarded_port=forwarded_port,
        listen_port=4662,
        latest_restart=latest_restart,
        now=now,
        restart_min_interval=RESTART_MIN_INTERVAL,
    )


def test_a_new_port_is_due_when_amuled_never_restarted() -> None:
    assert is_due(51820, latest_restart=None, now=instant_at(0))


def test_the_configured_port_is_never_due() -> None:
    assert not is_due(4662, latest_restart=None, now=instant_at(1000))


def test_a_new_port_within_the_window_waits() -> None:
    assert not is_due(51820, latest_restart=instant_at(1000), now=instant_at(1299))


def test_a_new_port_once_the_window_is_over_is_due() -> None:
    assert is_due(51820, latest_restart=instant_at(1000), now=instant_at(1300))
