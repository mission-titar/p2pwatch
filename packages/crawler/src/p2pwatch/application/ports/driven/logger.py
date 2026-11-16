"""``Logger``: the operator's diagnostic lines, at the four levels the core writes, a bug with its
trace."""

from abc import ABC, abstractmethod


class Logger(ABC):
    """Writes one line per call, ``message`` %-formatted with ``args`` as ``logging`` does."""

    @abstractmethod
    def debug(self, message: str, *args: object) -> None:
        """A detail the operator turns on to trace a run."""

    @abstractmethod
    def info(self, message: str, *args: object) -> None:
        """A step the operator may follow."""

    @abstractmethod
    def warning(self, message: str, *args: object) -> None:
        """A failure the crawler absorbs and retries."""

    @abstractmethod
    def error(self, message: str, *args: object) -> None:
        """A failure that loses work: a write, a step or a file skipped."""

    @abstractmethod
    def exception(self, message: str, *args: object, error: BaseException) -> None:
        """An exception nobody expected, a bug: an error line followed by ``error``'s trace."""
