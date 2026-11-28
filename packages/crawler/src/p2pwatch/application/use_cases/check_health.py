"""Checks the node's health, which Docker's healthcheck reads."""

from p2pwatch.application.ports.driven.health_endpoint_client import HealthEndpointClient
from p2pwatch.application.ports.driving.health_checker import HealthChecker


class CheckHealth(HealthChecker):
    """The node's health, as ``health_endpoint_client`` reads it."""

    def __init__(self, *, health_endpoint_client: HealthEndpointClient) -> None:
        self._health_endpoint_client = health_endpoint_client

    def check_health(self) -> bool:
        return self._health_endpoint_client.is_node_healthy()
