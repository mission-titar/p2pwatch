from abc import ABC, abstractmethod


class AmuleConfWriter(ABC):
    """Writes amule.conf, the file amuled reads its settings from when it starts."""

    @abstractmethod
    def write_amule_conf(self, conf: str, uid: int, gid: int) -> None:
        """Replaces amule.conf with ``conf`` at once, readable only by ``uid`` and ``gid``."""
