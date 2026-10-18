"""Entry point of port-sync: run as amule by its s6 service.

Each round puts gluetun's forwarded port in amule.conf, restarting amuled through s6 around it.
"""

import configparser
import logging
import os
import subprocess
import time

from p2pwatch_amule.adapters.driven.gluetun import forwarded_port
from p2pwatch_amule.adapters.driving import settings
from p2pwatch_amule.domain.conf import AMULE_CONF_PATH, tcp_listen_port, with_listen_port

AMULED_SERVICE_DIR = "/etc/services.d/amuled"

_logger = logging.getLogger("p2pwatch_amule.adapters.driving.port_sync")


def sync_listen_port_once(
    port_sync_settings: settings.Settings,
    latest_restart_monotonic: float | None,
    now_monotonic: float,
) -> float | None:
    """Run one round; return amuled's latest restart, `now_monotonic` if this round restarted it."""
    forwarded = forwarded_port(port_sync_settings.gluetun_control_url)
    if forwarded is None:
        return latest_restart_monotonic
    try:
        with open(AMULE_CONF_PATH) as handle:
            configured_port = tcp_listen_port(handle.read())
    except (OSError, ValueError, configparser.Error) as error:
        # The operator's file: a crash would only make s6 respawn port-sync every second.
        _logger.error("amule.conf's port is unreadable, amuled left as is (%s)", error)
        return latest_restart_monotonic
    if forwarded == configured_port:
        return latest_restart_monotonic
    if (
        latest_restart_monotonic is not None
        and now_monotonic - latest_restart_monotonic < port_sync_settings.restart_min_seconds
    ):
        return latest_restart_monotonic

    _logger.info(
        "gluetun forwards %d, amuled listens on %d: restarting amuled", forwarded, configured_port
    )
    try:
        # amuled flushes its config when it exits: a write while it runs could be overwritten.
        if _signal_amuled("-wD", "-T", "60000", "-d"):
            _write_listen_port(forwarded)
    except OSError as error:
        _logger.error("amule.conf was not written (%s)", error)
    finally:
        # A -d leaves amuled wanted down: without this -u it would stay down for good.
        _signal_amuled("-u")
    return now_monotonic


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    port_sync_settings = settings.load(os.environ)
    # A port-sync stopped between a -d and its -u left amuled down: bring it back first.
    _signal_amuled("-u")
    latest_restart_monotonic = None
    while True:
        latest_restart_monotonic = sync_listen_port_once(
            port_sync_settings, latest_restart_monotonic, time.monotonic()
        )
        time.sleep(port_sync_settings.poll_seconds)


def _signal_amuled(*options: str) -> bool:
    """Run `s6-svc <options>` on amuled; return whether it exited 0, logging why not."""
    result = subprocess.run(
        ["s6-svc", *options, AMULED_SERVICE_DIR], capture_output=True, text=True
    )
    if result.returncode != 0:
        command = " ".join(["s6-svc", *options])
        _logger.error("%s exited %d: %s", command, result.returncode, result.stderr.strip())
    return result.returncode == 0


def _write_listen_port(port: int) -> None:
    with open(AMULE_CONF_PATH) as handle:
        conf = handle.read()
    # Replaced, not rewritten in place: a failed write must not leave amuled a truncated file.
    temporary_path = AMULE_CONF_PATH + ".port-sync"
    with open(os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        handle.write(with_listen_port(conf, port))
    os.replace(temporary_path, AMULE_CONF_PATH)
    _logger.info("amule.conf now sets Port and UDPPort to %d", port)


if __name__ == "__main__":  # pragma: no cover
    main()
