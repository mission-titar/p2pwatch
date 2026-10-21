"""Entry point of port-sync: run as amule by its s6 service.

Each round puts gluetun's forwarded port in amule.conf, restarting amuled through s6 around it.
"""

from p2pwatch_amule.domain.amuled_restart import is_amuled_restart_due
from p2pwatch_amule.domain.conf import tcp_listen_port, with_listen_port
from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant
from p2pwatch_amule.domain.settings import PortSyncSettings
from p2pwatch_amule.ports.driven.amule_conf import AmuleConfReader, AmuleConfWriter
from p2pwatch_amule.ports.driven.forwarded_port_reader import ForwardedPortReader
from p2pwatch_amule.ports.driven.logger import Logger
from p2pwatch_amule.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.ports.driven.service_supervisor import ServiceSupervisor


def main(
    port_sync_settings: PortSyncSettings,
    *,
    forwarded_port_reader: ForwardedPortReader,
    amule_conf_reader: AmuleConfReader,
    amule_conf_writer: AmuleConfWriter,
    service_supervisor: ServiceSupervisor,
    monotonic_clock: MonotonicClock,
    logger: Logger,
) -> None:
    # A port-sync stopped between a stop and its start left amuled down: bring it back first.
    service_supervisor.start_amuled()
    latest_restart = None
    while True:
        latest_restart = _sync_listen_port_once(
            port_sync_settings,
            latest_restart,
            monotonic_clock.now(),
            forwarded_port_reader=forwarded_port_reader,
            amule_conf_reader=amule_conf_reader,
            amule_conf_writer=amule_conf_writer,
            service_supervisor=service_supervisor,
            logger=logger,
        )
        monotonic_clock.sleep(port_sync_settings.poll_interval)


def _sync_listen_port_once(
    port_sync_settings: PortSyncSettings,
    latest_restart: MonotonicInstant | None,
    now: MonotonicInstant,
    *,
    forwarded_port_reader: ForwardedPortReader,
    amule_conf_reader: AmuleConfReader,
    amule_conf_writer: AmuleConfWriter,
    service_supervisor: ServiceSupervisor,
    logger: Logger,
) -> MonotonicInstant | None:
    """Run one round; return amuled's latest restart, `now` if this round restarted it."""
    forwarded = forwarded_port_reader.read_forwarded_port()
    if forwarded is None:
        return latest_restart
    try:
        configured_port = tcp_listen_port(_read_existing_amule_conf(amule_conf_reader))
    except (OSError, ValueError) as error:
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
        if service_supervisor.stop_amuled():
            amule_conf_writer.write_amule_conf(
                with_listen_port(_read_existing_amule_conf(amule_conf_reader), forwarded),
                port_sync_settings.puid,
                port_sync_settings.pgid,
            )
            logger.info("amule.conf now sets Port and UDPPort to %d", forwarded)
    except OSError as error:
        logger.error("amule.conf was not written (%s)", error)
    finally:
        # A stop leaves amuled wanted down: without this start it would stay down for good.
        service_supervisor.start_amuled()
    return now


def _read_existing_amule_conf(amule_conf_reader: AmuleConfReader) -> str:
    amule_conf = amule_conf_reader.read_amule_conf()
    if amule_conf is None:
        raise FileNotFoundError("amule.conf does not exist")
    return amule_conf
