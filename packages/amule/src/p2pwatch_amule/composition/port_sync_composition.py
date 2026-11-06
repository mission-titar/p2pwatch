"""Port-sync's composition: parses its variables, then assembles and runs its loop."""

from collections.abc import Mapping
from urllib.request import OpenerDirector

from p2pwatch_amule.adapters.driven.amule_api_listen_port_client import AmuleApiListenPortClient
from p2pwatch_amule.adapters.driven.gluetun_forwarded_port_client import (
    GluetunForwardedPortClient,
)
from p2pwatch_amule.adapters.driven.stdlib_logger import StdlibLogger
from p2pwatch_amule.application.port_sync_lifecycle import PortSyncLifecycle
from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch_amule.application.ports.driving.port_sync_loop_runner import PortSyncLoopRunner
from p2pwatch_amule.domain.settings import parse_port_sync_settings

_GLUETUN_TIMEOUT_SECONDS = 10
_AMULE_API_TIMEOUT_SECONDS = 10


class PortSyncComposition(PortSyncLoopRunner):
    """Parses port-sync's variables, then assembles and runs ``PortSyncLifecycle`` (composition
    root)."""

    def __init__(
        self,
        *,
        env: Mapping[str, str],
        amule_conf_reader: AmuleConfReader,
        gluetun_url_opener: OpenerDirector,
        amule_api_url: str,
        amule_api_url_opener: OpenerDirector,
        monotonic_clock: MonotonicClock,
    ) -> None:
        self._env = env
        self._amule_conf_reader = amule_conf_reader
        self._gluetun_url_opener = gluetun_url_opener
        self._amule_api_url = amule_api_url
        self._amule_api_url_opener = amule_api_url_opener
        self._monotonic_clock = monotonic_clock

    def run_port_sync_loop(self) -> None:
        port_sync_settings = parse_port_sync_settings(self._env)
        PortSyncLifecycle(
            port_sync_settings=port_sync_settings,
            forwarded_port_client=GluetunForwardedPortClient(
                control_url=port_sync_settings.gluetun_control_url,
                timeout_seconds=_GLUETUN_TIMEOUT_SECONDS,
                url_opener=self._gluetun_url_opener,
            ),
            listen_port_client=AmuleApiListenPortClient(
                api_url=self._amule_api_url,
                api_password=port_sync_settings.api_password,
                timeout_seconds=_AMULE_API_TIMEOUT_SECONDS,
                url_opener=self._amule_api_url_opener,
            ),
            amule_conf_reader=self._amule_conf_reader,
            monotonic_clock=self._monotonic_clock,
            logger=StdlibLogger(PortSyncLifecycle.__module__),
        ).run()
