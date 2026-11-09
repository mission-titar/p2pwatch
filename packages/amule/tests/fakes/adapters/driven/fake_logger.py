from dataclasses import dataclass
from typing import Literal

from p2pwatch_amule.application.ports.driven.logger import Logger


@dataclass(kw_only=True, frozen=True)
class LoggedLine:
    level: Literal["info", "error"]
    message: str
    error: Exception | None = None


class FakeLogger(Logger):
    """Keeps each line, its arguments formatted in as ``logging`` does, and its error if any."""

    def __init__(self) -> None:
        self.lines: list[LoggedLine] = []

    def info(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine(level="info", message=message % args))

    def error(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine(level="error", message=message % args))

    def error_with_trace(self, message: str, *args: object, error: Exception) -> None:
        self.lines.append(LoggedLine(level="error", message=message % args, error=error))
