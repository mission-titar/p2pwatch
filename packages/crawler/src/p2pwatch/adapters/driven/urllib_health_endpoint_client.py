import http.client
import logging
from urllib.error import HTTPError
from urllib.request import OpenerDirector

from p2pwatch.application.ports.driven.health_endpoint_client import HealthEndpointClient

_logger = logging.getLogger(__name__)


class UrllibHealthEndpointClient(HealthEndpointClient):
    """``GET <url>`` by ``url_opener``: healthy on a ``200``."""

    def __init__(self, *, url: str, timeout_seconds: float, url_opener: OpenerDirector) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._url_opener = url_opener

    def is_node_healthy(self) -> bool:
        try:
            with self._url_opener.open(self._url, timeout=self._timeout_seconds) as response:
                status: int = response.status
        except HTTPError as error:  # before OSError, its base: the webui did answer
            status = error.code
        except (OSError, http.client.HTTPException) as error:
            # Refused until the webui serves; URLError and timeouts are OSErrors.
            _logger.warning("the webui does not answer /health (%s)", error)
            return False
        if status != 200:
            _logger.warning("the webui answers /health with %d", status)
            return False
        return True
