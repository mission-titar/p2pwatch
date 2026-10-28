from p2pwatch_amule.application.ports.driven.amule_conf_reader import AmuleConfReader
from p2pwatch_amule.application.ports.driven.amule_conf_writer import AmuleConfWriter
from p2pwatch_amule.domain.identifiers import Gid, Uid


class FakeAmuleConfStore(AmuleConfReader, AmuleConfWriter):
    """amule.conf held as text, ``None`` when absent; records each read and each write in
    ``actions``, or raises ``read_error`` on a read and ``write_error`` on a write."""

    def __init__(self, actions: list[str]) -> None:
        self.actions = actions
        self.conf: str | None = None
        self.read_error: OSError | None = None
        self.write_error: OSError | None = None

    def read_amule_conf(self) -> str | None:
        if self.read_error is not None:
            raise self.read_error
        self.actions.append("read amule.conf")
        return self.conf

    def set_amule_conf(self, conf: str, uid: Uid, gid: Gid) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.conf = conf
        self.actions.append(f"write amule.conf as {uid}:{gid}")
