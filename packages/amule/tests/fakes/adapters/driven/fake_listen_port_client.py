from p2pwatch_amule.application.ports.driven.listen_port_client import ListenPortClient
from p2pwatch_amule.domain.listen_port_error import ListenPortError


class FakeListenPortClient(ListenPortClient):
    """Records each port it is asked for in ``actions``, then raises ``error`` when set."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions
        self.error: ListenPortError | None = None

    def set_listen_port(self, port: int) -> None:
        self.actions.append(f"set listen port {port}")
        if self.error is not None:
            raise self.error
