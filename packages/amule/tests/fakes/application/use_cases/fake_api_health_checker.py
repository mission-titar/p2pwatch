from p2pwatch_amule.application.ports.driving.api_health_checker import ApiHealthChecker


class FakeApiHealthChecker(ApiHealthChecker):
    """Returns ``is_healthy``, counting its checks."""

    def __init__(self) -> None:
        self.is_healthy = True
        self.checks = 0

    def check_api_health(self) -> bool:
        self.checks += 1
        return self.is_healthy
