"""Keeps amuled's listen port on gluetun's forwarded port: each round reads it and sets it live
through amuleapi, and leaves amuled on its port until the next poll when the round fails."""

from p2pwatch_amule.application.ports.driven.forwarded_port_client import ForwardedPortClient
from p2pwatch_amule.application.ports.driven.listen_port_client import ListenPortClient
from p2pwatch_amule.application.ports.driven.logger import Logger
from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.domain.listen_port_error import ApiNotReadyError, ListenPortRejectedError
from p2pwatch_amule.domain.settings import PortSyncSettings


class PortSyncLifecycle:
    """Polls every ``poll_interval``, a round's failure logged and retried at the next poll;
    port-sync's root, behind no port."""

    def __init__(
        self,
        *,
        port_sync_settings: PortSyncSettings,
        forwarded_port_client: ForwardedPortClient,
        listen_port_client: ListenPortClient,
        monotonic_clock: MonotonicClock,
        logger: Logger,
    ) -> None:
        self._port_sync_settings = port_sync_settings
        self._forwarded_port_client = forwarded_port_client
        self._listen_port_client = listen_port_client
        self._monotonic_clock = monotonic_clock
        self._logger = logger

    def run(self) -> None:
        while True:
            self._run_round()
            self._monotonic_clock.sleep(self._port_sync_settings.poll_interval)

    def _run_round(self) -> None:
        try:
            self._sync_listen_port_once()
        except Exception as error:  # a bug included: exiting restarts amuled with the container
            self._logger.error_with_trace(
                "the round failed, amuled stays on its port until the next poll", error=error
            )

    def _sync_listen_port_once(self) -> None:
        forwarded_port = self._forwarded_port_client.read_forwarded_port()
        if forwarded_port is None:
            return
        try:
            listen_port = self._listen_port_client.read_listen_port()
        except ApiNotReadyError as error:
            self._log_not_ready(forwarded_port=forwarded_port, error=error)
            return
        if forwarded_port == listen_port:
            return
        try:
            self._listen_port_client.set_listen_port(forwarded_port)
        except ApiNotReadyError as error:
            self._log_not_ready(forwarded_port=forwarded_port, error=error)
        except ListenPortRejectedError as error:
            self._logger.error(
                "amuleapi rejected %d, amuled stays on %d (%s)", forwarded_port, listen_port, error
            )
        else:
            self._logger.info(
                "gluetun forwards %d, amuled listened on %d: set live", forwarded_port, listen_port
            )

    def _log_not_ready(self, *, forwarded_port: int, error: ApiNotReadyError) -> None:
        # The first round runs before amuleapi listens: an expected wait, no error and no trace.
        self._logger.info(
            "amuleapi is not ready, %d waits for the next poll (%s)", forwarded_port, error
        )
