from p2pwatch_amule.application.ports.driven.api_health_client import ApiHealthClient


class FakeApiHealthClient(ApiHealthClient):
    """Returns ``is_ready``, counting its reads."""

    def __init__(self) -> None:
        self.is_ready = True
        self.reads = 0

    def is_api_ready(self) -> bool:
        self.reads += 1
        return self.is_ready
