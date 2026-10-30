from dataclasses import dataclass
from typing import Literal

from p2pwatch.application.ports.driven.logger import Logger


@dataclass(kw_only=True, frozen=True)
class LoggedLine:
    level: Literal["debug", "info", "warning", "error"]
    message: str


class FakeLogger(Logger):
    """Keeps each line, its arguments formatted in as ``logging`` does."""

    def __init__(self) -> None:
        self.lines: list[LoggedLine] = []

    def debug(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine(level="debug", message=_formatted(message, args=args)))

    def info(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine(level="info", message=_formatted(message, args=args)))

    def warning(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine(level="warning", message=_formatted(message, args=args)))

    def error(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine(level="error", message=_formatted(message, args=args)))


def _formatted(message: str, *, args: tuple[object, ...]) -> str:
    return message % args if args else message
