from collections.abc import Callable

from p2pwatch_amule.application.ports.driven.forwarded_port_client import ForwardedPortClient


class FakeForwardedPortClient(ForwardedPortClient):
    """Returns ``forwarded_port``, after calling ``on_read``."""

    def __init__(self) -> None:
        self.forwarded_port: int | None = 51820
        self.on_read: Callable[[], None] = lambda: None

    def read_forwarded_port(self) -> int | None:
        self.on_read()
        return self.forwarded_port
