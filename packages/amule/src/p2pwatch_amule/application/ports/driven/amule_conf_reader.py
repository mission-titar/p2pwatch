from abc import ABC, abstractmethod


class AmuleConfReader(ABC):
    """Reads amule.conf, the file amuled reads its settings from when it starts."""

    @abstractmethod
    def read_amule_conf(self) -> str | None:
        """amule.conf's text, ``None`` when it does not exist; raises ``OSError`` otherwise."""
