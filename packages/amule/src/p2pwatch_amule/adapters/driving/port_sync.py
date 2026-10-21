"""Entry point of port-sync: run as amule by its s6 service.

Each round puts gluetun's forwarded port in amule.conf, restarting amuled through s6 around it.
"""

import configparser
import logging
import os
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

from p2pwatch_amule.adapters.driven.gluetun import forwarded_port
from p2pwatch_amule.domain.conf import tcp_listen_port, with_listen_port
from p2pwatch_amule.domain.settings import PortSyncSettings, parse_port_sync_settings

_logger = logging.getLogger("p2pwatch_amule.adapters.driving.port_sync")


def sync_listen_port_once(
    port_sync_settings: PortSyncSettings,
    latest_restart_monotonic: float | None,
    now_monotonic: float,
    *,
    amule_conf_path: Path,
    amuled_service_directory: Path,
) -> float | None:
    """Run one round; return amuled's latest restart, `now_monotonic` if this round restarted it."""
    forwarded = forwarded_port(port_sync_settings.gluetun_control_url)
    if forwarded is None:
        return latest_restart_monotonic
    try:
        with open(amule_conf_path) as handle:
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
        if _signal_amuled(amuled_service_directory, "-wD", "-T", "60000", "-d"):
            _write_listen_port(amule_conf_path, forwarded)
    except OSError as error:
        _logger.error("amule.conf was not written (%s)", error)
    finally:
        # A -d leaves amuled wanted down: without this -u it would stay down for good.
        _signal_amuled(amuled_service_directory, "-u")
    return now_monotonic


def main(env: Mapping[str, str], *, amule_conf_path: Path, amuled_service_directory: Path) -> None:
    port_sync_settings = parse_port_sync_settings(env)
    # A port-sync stopped between a -d and its -u left amuled down: bring it back first.
    _signal_amuled(amuled_service_directory, "-u")
    latest_restart_monotonic = None
    while True:
        latest_restart_monotonic = sync_listen_port_once(
            port_sync_settings,
            latest_restart_monotonic,
            time.monotonic(),
            amule_conf_path=amule_conf_path,
            amuled_service_directory=amuled_service_directory,
        )
        time.sleep(port_sync_settings.poll_seconds)


def _signal_amuled(amuled_service_directory: Path, *options: str) -> bool:
    """Run `s6-svc <options>` on amuled; return whether it exited 0, logging why not."""
    result = subprocess.run(
        ["s6-svc", *options, str(amuled_service_directory)], capture_output=True, text=True
    )
    if result.returncode != 0:
        command = " ".join(["s6-svc", *options])
        _logger.error("%s exited %d: %s", command, result.returncode, result.stderr.strip())
    return result.returncode == 0


def _write_listen_port(amule_conf_path: Path, port: int) -> None:
    with open(amule_conf_path) as handle:
        conf = handle.read()
    # Replaced, not rewritten in place: a failed write must not leave amuled a truncated file.
    temporary_path = amule_conf_path.with_name(amule_conf_path.name + ".port-sync")
    with open(os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        handle.write(with_listen_port(conf, port))
    os.replace(temporary_path, amule_conf_path)
    _logger.info("amule.conf now sets Port and UDPPort to %d", port)
