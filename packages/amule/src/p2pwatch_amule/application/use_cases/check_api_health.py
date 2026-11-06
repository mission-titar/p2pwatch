"""Checks amuleapi's health, which the container's healthcheck reads."""

from p2pwatch_amule.application.ports.driven.api_health_client import ApiHealthClient
from p2pwatch_amule.application.ports.driving.api_health_checker import ApiHealthChecker


class CheckApiHealth(ApiHealthChecker):
    """amuleapi's health, as ``api_health_client`` reads it."""

    def __init__(self, *, api_health_client: ApiHealthClient) -> None:
        self._api_health_client = api_health_client

    def check_api_health(self) -> bool:
        return self._api_health_client.is_api_ready()
