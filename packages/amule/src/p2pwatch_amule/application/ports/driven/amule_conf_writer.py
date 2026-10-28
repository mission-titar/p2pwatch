from abc import ABC, abstractmethod

from p2pwatch_amule.domain.identifiers import Gid, Uid


class AmuleConfWriter(ABC):
    """Writes amule.conf, the file amuled reads its settings from when it starts."""

    @abstractmethod
    def set_amule_conf(self, conf: str, uid: Uid, gid: Gid) -> None:
        """Replaces amule.conf with ``conf`` at once, readable only by ``uid`` and ``gid``."""
