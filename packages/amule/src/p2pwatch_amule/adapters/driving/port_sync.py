"""Entry point of port-sync: run as amule by its s6 service.

Each round puts gluetun's forwarded port in amule.conf, restarting amuled through s6 around it.
"""

import configparser
import os
import subprocess
from pathlib import Path

from p2pwatch_amule.domain.amuled_restart import is_amuled_restart_due
from p2pwatch_amule.domain.conf import tcp_listen_port, with_listen_port
from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant
from p2pwatch_amule.domain.settings import PortSyncSettings
from p2pwatch_amule.ports.driven.forwarded_port_reader import ForwardedPortReader
from p2pwatch_amule.ports.driven.logger import Logger
from p2pwatch_amule.ports.driven.monotonic_clock import MonotonicClock


def sync_listen_port_once(
    port_sync_settings: PortSyncSettings,
    latest_restart: MonotonicInstant | None,
    now: MonotonicInstant,
    *,
    amule_conf_path: Path,
    amuled_service_directory: Path,
    forwarded_port_reader: ForwardedPortReader,
    logger: Logger,
) -> MonotonicInstant | None:
    """Run one round; return amuled's latest restart, `now` if this round restarted it."""
    forwarded = forwarded_port_reader.read_forwarded_port()
    if forwarded is None:
        return latest_restart
    try:
        with open(amule_conf_path) as handle:
            configured_port = tcp_listen_port(handle.read())
    except (OSError, ValueError, configparser.Error) as error:
        # The operator's file: a crash would only make s6 respawn port-sync every second.
        logger.error("amule.conf's port is unreadable, amuled left as is (%s)", error)
        return latest_restart
    if not is_amuled_restart_due(
        forwarded_port=forwarded,
        configured_port=configured_port,
        latest_restart=latest_restart,
        now=now,
        restart_min_interval=port_sync_settings.restart_min_interval,
    ):
        return latest_restart

    logger.info(
        "gluetun forwards %d, amuled listens on %d: restarting amuled", forwarded, configured_port
    )
    try:
        # amuled flushes its config when it exits: a write while it runs could be overwritten.
        if _signal_amuled(amuled_service_directory, logger, "-wD", "-T", "60000", "-d"):
            _write_listen_port(amule_conf_path, forwarded, logger)
    except OSError as error:
        logger.error("amule.conf was not written (%s)", error)
    finally:
        # A -d leaves amuled wanted down: without this -u it would stay down for good.
        _signal_amuled(amuled_service_directory, logger, "-u")
    return now


def main(
    port_sync_settings: PortSyncSettings,
    *,
    amule_conf_path: Path,
    amuled_service_directory: Path,
    monotonic_clock: MonotonicClock,
    forwarded_port_reader: ForwardedPortReader,
    logger: Logger,
) -> None:
    # A port-sync stopped between a -d and its -u left amuled down: bring it back first.
    _signal_amuled(amuled_service_directory, logger, "-u")
    latest_restart = None
    while True:
        latest_restart = sync_listen_port_once(
            port_sync_settings,
            latest_restart,
            monotonic_clock.now(),
            amule_conf_path=amule_conf_path,
            amuled_service_directory=amuled_service_directory,
            forwarded_port_reader=forwarded_port_reader,
            logger=logger,
        )
        monotonic_clock.sleep(port_sync_settings.poll_interval)


def _signal_amuled(amuled_service_directory: Path, logger: Logger, *options: str) -> bool:
    """Run `s6-svc <options>` on amuled; return whether it exited 0, logging why not."""
    result = subprocess.run(
        ["s6-svc", *options, str(amuled_service_directory)], capture_output=True, text=True
    )
    if result.returncode != 0:
        command = " ".join(["s6-svc", *options])
        logger.error("%s exited %d: %s", command, result.returncode, result.stderr.strip())
    return result.returncode == 0


def _write_listen_port(amule_conf_path: Path, port: int, logger: Logger) -> None:
    with open(amule_conf_path) as handle:
        conf = handle.read()
    # Replaced, not rewritten in place: a failed write must not leave amuled a truncated file.
    temporary_path = amule_conf_path.with_name(amule_conf_path.name + ".port-sync")
    with open(os.open(temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        handle.write(with_listen_port(conf, port))
    os.replace(temporary_path, amule_conf_path)
    logger.info("amule.conf now sets Port and UDPPort to %d", port)
