from p2pwatch.application.ports.driven.health_endpoint_client import HealthEndpointClient


class FakeHealthEndpointClient(HealthEndpointClient):
    """Returns ``is_healthy``, counting its reads."""

    def __init__(self, *, is_healthy: bool) -> None:
        self.is_healthy = is_healthy
        self.reads = 0

    def is_node_healthy(self) -> bool:
        self.reads += 1
        return self.is_healthy
