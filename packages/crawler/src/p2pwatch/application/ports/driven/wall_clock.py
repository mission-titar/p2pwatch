"""Time of day, injectable: ``WallClock`` stamps."""

from abc import ABC, abstractmethod
from datetime import datetime


class WallClock(ABC):
    """The UTC time of day, aware: every stamp a row, an event or a display carries."""

    @abstractmethod
    def now(self) -> datetime:
        """The current UTC time, aware; callable from any thread, with no running event loop."""
