from dataclasses import dataclass
from typing import Literal

from p2pwatch_amule.application.ports.driven.logger import Logger


@dataclass(frozen=True)
class LoggedLine:
    level: Literal["info", "error"]
    message: str


class FakeLogger(Logger):
    """Keeps each line, its arguments formatted in as ``logging`` does."""

    def __init__(self) -> None:
        self.lines: list[LoggedLine] = []

    def info(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("info", message % args))

    def error(self, message: str, *args: object) -> None:
        self.lines.append(LoggedLine("error", message % args))
