"""Keeps amuled's listen port on gluetun's forwarded port: each round puts it in amule.conf,
restarting amuled around the write."""

from p2pwatch_amule.domain.amuled_restart import is_amuled_restart_due
from p2pwatch_amule.domain.conf import tcp_listen_port, with_listen_port
from p2pwatch_amule.domain.monotonic_instant import MonotonicInstant
from p2pwatch_amule.domain.settings import PortSyncSettings
from p2pwatch_amule.ports.driven.amule_conf import AmuleConfReader, AmuleConfWriter
from p2pwatch_amule.ports.driven.forwarded_port_reader import ForwardedPortReader
from p2pwatch_amule.ports.driven.logger import Logger
from p2pwatch_amule.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.ports.driven.service_supervisor import ServiceSupervisor


class RunPortSyncLoop:
    """Polls every ``poll_interval``, restarts amuled at most once per ``restart_min_interval``;
    the root of port-sync's graph, behind no port, as ``RunCrawler``."""

    def __init__(
        self,
        *,
        port_sync_settings: PortSyncSettings,
        forwarded_port_reader: ForwardedPortReader,
        amule_conf_reader: AmuleConfReader,
        amule_conf_writer: AmuleConfWriter,
        service_supervisor: ServiceSupervisor,
        monotonic_clock: MonotonicClock,
        logger: Logger,
    ) -> None:
        self._port_sync_settings = port_sync_settings
        self._forwarded_port_reader = forwarded_port_reader
        self._amule_conf_reader = amule_conf_reader
        self._amule_conf_writer = amule_conf_writer
        self._service_supervisor = service_supervisor
        self._monotonic_clock = monotonic_clock
        self._logger = logger

    def run_port_sync_loop(self) -> None:
        # A port-sync stopped between a stop and its start left amuled down: bring it back first.
        self._service_supervisor.start_amuled()
        latest_restart = None
        while True:
            latest_restart = self._sync_listen_port_once(
                latest_restart, self._monotonic_clock.now()
            )
            self._monotonic_clock.sleep(self._port_sync_settings.poll_interval)

    def _sync_listen_port_once(
        self, latest_restart: MonotonicInstant | None, now: MonotonicInstant
    ) -> MonotonicInstant | None:
        """Run one round; return amuled's latest restart, `now` if this round restarted it."""
        forwarded = self._forwarded_port_reader.read_forwarded_port()
        if forwarded is None:
            return latest_restart
        try:
            configured_port = tcp_listen_port(self._read_existing_amule_conf())
        except (OSError, ValueError) as error:
            # The operator's file: a crash would only make s6 respawn port-sync every second.
            self._logger.error("amule.conf's port is unreadable, amuled left as is (%s)", error)
            return latest_restart
        if not is_amuled_restart_due(
            forwarded_port=forwarded,
            configured_port=configured_port,
            latest_restart=latest_restart,
            now=now,
            restart_min_interval=self._port_sync_settings.restart_min_interval,
        ):
            return latest_restart

        self._logger.info(
            "gluetun forwards %d, amuled listens on %d: restarting amuled",
            forwarded,
            configured_port,
        )
        try:
            # amuled flushes its config when it exits: a write while it runs could be overwritten.
            if self._service_supervisor.stop_amuled():
                self._amule_conf_writer.write_amule_conf(
                    with_listen_port(self._read_existing_amule_conf(), forwarded),
                    self._port_sync_settings.puid,
                    self._port_sync_settings.pgid,
                )
                self._logger.info("amule.conf now sets Port and UDPPort to %d", forwarded)
        except OSError as error:
            self._logger.error("amule.conf was not written (%s)", error)
        finally:
            # A stop leaves amuled wanted down: without this start it would stay down for good.
            self._service_supervisor.start_amuled()
        return now

    def _read_existing_amule_conf(self) -> str:
        amule_conf = self._amule_conf_reader.read_amule_conf()
        if amule_conf is None:
            raise FileNotFoundError("amule.conf does not exist")
        return amule_conf
