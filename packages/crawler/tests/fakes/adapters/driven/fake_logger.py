from dataclasses import dataclass
from typing import Literal

from p2pwatch.application.ports.driven.logger import Logger


@dataclass(frozen=True)
class LoggedLine:
    level: Literal["info", "warning", "error"]
    message: str


class FakeLogger(Logger):
    """Keeps each line, its arguments formatted in as ``logging`` does."""

    def __init__(self) -> None:
        self.lines: list[LoggedLine] = []

    def info(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("info", _formatted(message, args)))

    def warning(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("warning", _formatted(message, args)))

    def error(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("error", _formatted(message, args)))


def _formatted(message: str, args: tuple[object, ...]) -> str:
    return message % args if args else message
