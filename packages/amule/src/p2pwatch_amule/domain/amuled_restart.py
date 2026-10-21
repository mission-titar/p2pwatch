"""Port-sync's decision: whether amuled restarts to listen on gluetun's forwarded port."""

from datetime import timedelta

from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant


def is_amuled_restart_due(
    *,
    forwarded_port: int,
    listen_port: int,
    latest_restart: MonotonicInstant | None,
    now: MonotonicInstant,
    restart_min_interval: timedelta,
) -> bool:
    """Return whether the ports differ and amuled's latest restart is `restart_min_interval` old."""
    if forwarded_port == listen_port:
        return False
    return latest_restart is None or now - latest_restart >= restart_min_interval
