"""Keeps amuled's listen port on gluetun's forwarded port: each round sets it live through
amuleapi, and leaves amuled on its port until the next poll when amuleapi is not ready or rejects
it."""

from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.forwarded_port_client import ForwardedPortClient
from p2pwatch_amule.application.ports.driven.listen_port_client import ListenPortClient
from p2pwatch_amule.application.ports.driven.logger import Logger
from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.domain.conf import tcp_listen_port
from p2pwatch_amule.domain.listen_port_error import ApiNotReadyError, ListenPortRejectedError
from p2pwatch_amule.domain.settings import PortSyncSettings


class PortSyncLifecycle:
    """Polls every ``poll_interval``; a failure of amuleapi other than not ready or a rejection
    ends the loop; port-sync's root, behind no port."""

    def __init__(
        self,
        *,
        port_sync_settings: PortSyncSettings,
        forwarded_port_client: ForwardedPortClient,
        listen_port_client: ListenPortClient,
        amule_conf_reader: AmuleConfReader,
        monotonic_clock: MonotonicClock,
        logger: Logger,
    ) -> None:
        self._port_sync_settings = port_sync_settings
        self._forwarded_port_client = forwarded_port_client
        self._listen_port_client = listen_port_client
        self._amule_conf_reader = amule_conf_reader
        self._monotonic_clock = monotonic_clock
        self._logger = logger

    def run(self) -> None:
        while True:
            self._sync_listen_port_once()
            self._monotonic_clock.sleep(self._port_sync_settings.poll_interval)

    def _sync_listen_port_once(self) -> None:
        forwarded_port = self._forwarded_port_client.read_forwarded_port()
        if forwarded_port is None:
            return
        try:
            amule_conf = self._amule_conf_reader.read_amule_conf()
            if amule_conf is None:
                self._logger.error("amule.conf does not exist, amuled left as is")
                return
            listen_port = tcp_listen_port(amule_conf)
        except (OSError, ValueError) as error:
            # The operator's file: raising would restart the container, amuled included.
            self._logger.error("amule.conf's port is unreadable, amuled left as is (%s)", error)
            return
        if forwarded_port == listen_port:
            return
        try:
            self._listen_port_client.set_listen_port(forwarded_port)
        except ApiNotReadyError as error:
            # The first round runs before amuleapi listens: raising would restart the container.
            self._logger.info(
                "amuleapi is not ready, %d waits for the next poll (%s)", forwarded_port, error
            )
        except ListenPortRejectedError as error:
            self._logger.error(
                "amuleapi rejected %d, amuled stays on %d (%s)", forwarded_port, listen_port, error
            )
        else:
            self._logger.info(
                "gluetun forwards %d, amuled listened on %d: set live", forwarded_port, listen_port
            )
