from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.amule_conf_writer import AmuleConfWriter


class FakeAmuleConfStore(AmuleConfReader, AmuleConfWriter):
    """amule.conf held as text, ``None`` when absent; records each read and each write in
    ``actions``, or raises ``write_error`` on a write."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions
        self.conf: str | None = None
        self.write_error: OSError | None = None

    def read_amule_conf(self) -> str | None:
        self.actions.append("read amule.conf")
        return self.conf

    def write_amule_conf(self, conf: str, uid: int, gid: int) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.conf = conf
        self.actions.append(f"write amule.conf as {uid}:{gid}")
