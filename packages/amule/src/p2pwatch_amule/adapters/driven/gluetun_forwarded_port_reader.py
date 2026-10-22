import http.client
import json
from urllib.request import OpenerDirector

from p2pwatch_amule.application.ports.driven.forwarded_port_reader import ForwardedPortReader
from p2pwatch_amule.application.ports.driven.logger import Logger


class GluetunForwardedPortReader(ForwardedPortReader):
    """``GET <control_url>/v1/portforward`` → ``{"port": N}``, by ``url_opener``; None unless N is
    a TCP port."""

    def __init__(
        self,
        *,
        control_url: str,
        timeout_seconds: float,
        logger: Logger,
        url_opener: OpenerDirector,
    ) -> None:
        self._url = control_url.rstrip("/") + "/v1/portforward"
        self._timeout_seconds = timeout_seconds
        self._logger = logger
        self._url_opener = url_opener

    def read_forwarded_port(self) -> int | None:
        try:
            with self._url_opener.open(self._url, timeout=self._timeout_seconds) as response:
                body: bytes = response.read()
        except (OSError, http.client.HTTPException) as error:
            # URLError, HTTPError and timeouts are OSErrors; a garbled reply is an HTTPException.
            self._logger.warning("gluetun's control server is unavailable (%s)", error)
            return None
        try:
            port = json.loads(body).get("port")
        except (ValueError, AttributeError):
            port = None
        if not (type(port) is int and 0 < port <= 65535):
            self._logger.warning("gluetun reports no forwarded port (%r)", body[:100])
            return None
        return port
