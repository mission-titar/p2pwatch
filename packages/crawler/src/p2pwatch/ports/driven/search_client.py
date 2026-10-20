"""What the crawler expects from any client that searches; its errors are in ``client_errors``."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from p2pwatch.domain.observation import ReportedFile


@dataclass(frozen=True)
class SearchAnswer:
    """What one search found, and how many of its results the client could not read."""

    reported_files: tuple[ReportedFile, ...]
    skipped_result_count: int


class SearchClient(ABC):
    """Searches a keyword on one of its channels."""

    @abstractmethod
    def channels(self) -> tuple[str, ...]:
        """The channels it searches: opaque names the core never tests."""

    @abstractmethod
    async def search(self, keyword: str, channel: str, budget_seconds: float) -> SearchAnswer:
        """Returns once the client signals the end, or ``budget_seconds`` after the search's
        network start at the latest."""
