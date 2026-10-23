"""``Logger``: the operator's diagnostic lines, at the two levels port-sync writes."""

from abc import ABC, abstractmethod


class Logger(ABC):
    """Writes one line per call, ``message`` %-formatted with ``args`` as ``logging`` does."""

    @abstractmethod
    def info(self, message: str, *args: object) -> None:
        """A step the operator may follow."""

    @abstractmethod
    def error(self, message: str, *args: object) -> None:
        """A failure that loses work: a command or a write that did not happen."""
