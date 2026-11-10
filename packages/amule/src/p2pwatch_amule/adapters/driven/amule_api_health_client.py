import http.client
import json
import logging
from urllib.request import OpenerDirector

from p2pwatch_amule.application.ports.driven.api_health_client import ApiHealthClient

_logger = logging.getLogger(__name__)


class AmuleApiHealthClient(ApiHealthClient):
    """``GET <api_url>/api/v1/health`` by ``url_opener``: healthy on a ``200`` whose
    ``ec_connected`` is true."""

    def __init__(
        self,
        *,
        api_url: str,
        timeout_seconds: float,
        url_opener: OpenerDirector,
    ) -> None:
        self._url = api_url + "/api/v1/health"
        self._timeout_seconds = timeout_seconds
        self._url_opener = url_opener

    def is_api_healthy(self) -> bool:
        try:
            with self._url_opener.open(self._url, timeout=self._timeout_seconds) as response:
                status: int = response.status
                body: bytes = response.read()
        except (OSError, http.client.HTTPException) as error:
            # Refused before amuleapi's EC login; URLError, HTTPError and timeouts are OSErrors.
            _logger.warning("amuleapi is unavailable (%s)", error)
            return False
        try:
            ec_connected = json.loads(body).get("ec_connected")
        except (ValueError, RecursionError, AttributeError):
            ec_connected = None
        if status != 200 or ec_connected is not True:
            _logger.warning("amuleapi reports no link to amuled (%d %r)", status, body[:100])
            return False
        return True
