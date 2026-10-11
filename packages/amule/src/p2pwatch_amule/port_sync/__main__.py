"""Entry point `python -m p2pwatch_amule.port_sync`: run as amule by its s6 service.

Each round puts gluetun's forwarded port in amule.conf, restarting amuled through s6 around it.
"""

import configparser
import logging
import os
import subprocess
import time

from p2pwatch_amule.config.conf import CONFIG_DIR, listen_port, with_listen_port
from p2pwatch_amule.port_sync import settings
from p2pwatch_amule.port_sync.gluetun import forwarded_port

AMULED_SERVICE_DIR = "/etc/services.d/amuled"
CONF_PATH = os.path.join(CONFIG_DIR, "amule.conf")

_logger = logging.getLogger("p2pwatch_amule.port_sync")


def sync_listen_port_once(
    config: settings.Settings, last_restart: float | None, now: float
) -> float | None:
    """Run one round; return when amuled was last restarted, `now` if this round did."""
    forwarded = forwarded_port(config.gluetun_control_url)
    if forwarded is None:
        return last_restart
    try:
        with open(CONF_PATH) as handle:
            configured = listen_port(handle.read())
    except (OSError, ValueError, configparser.Error) as error:
        # The operator's file: a crash would only make s6 respawn port-sync every second.
        _logger.error("amule.conf's port is unreadable, amuled left as is (%s)", error)
        return last_restart
    if forwarded == configured:
        return last_restart
    if last_restart is not None and now - last_restart < config.restart_min_seconds:
        return last_restart

    _logger.info(
        "gluetun forwards %d, amuled listens on %d: restarting amuled", forwarded, configured
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
    return now


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = settings.load(os.environ)
    # A port-sync stopped between a -d and its -u left amuled down: bring it back first.
    _signal_amuled("-u")
    last_restart = None
    while True:
        last_restart = sync_listen_port_once(config, last_restart, time.monotonic())
        time.sleep(config.poll_seconds)


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
    with open(CONF_PATH) as handle:
        conf = handle.read()
    # Replaced, not rewritten in place: a failed write must not leave amuled a truncated file.
    temporary = CONF_PATH + ".port-sync"
    with open(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        handle.write(with_listen_port(conf, port))
    os.replace(temporary, CONF_PATH)
    _logger.info("amule.conf now sets Port and UDPPort to %d", port)


if __name__ == "__main__":  # pragma: no cover
    main()
