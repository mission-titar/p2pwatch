from p2pwatch.application.ports.driving.health_checker import HealthChecker


class FakeHealthChecker(HealthChecker):
    """Returns ``is_healthy``, counting its checks."""

    def __init__(self, *, is_healthy: bool = True) -> None:
        self.is_healthy = is_healthy
        self.checks = 0

    def check_health(self) -> bool:
        self.checks += 1
        return self.is_healthy
