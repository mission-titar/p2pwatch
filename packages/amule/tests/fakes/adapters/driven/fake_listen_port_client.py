from p2pwatch_amule.application.ports.driven.listen_port_client import ListenPortClient


class FakeListenPortClient(ListenPortClient):
    """amuled's ``listen_port``, read unless ``read_error`` is set, set unless ``set_error`` is;
    records each read and each port it is asked for in ``actions``."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions
        self.listen_port = 4662
        self.read_error: Exception | None = None
        self.set_error: Exception | None = None

    def read_listen_port(self) -> int:
        self.actions.append("read listen port")
        if self.read_error is not None:
            raise self.read_error
        return self.listen_port

    def set_listen_port(self, port: int) -> None:
        self.actions.append(f"set listen port {port}")
        if self.set_error is not None:
            raise self.set_error
        self.listen_port = port
