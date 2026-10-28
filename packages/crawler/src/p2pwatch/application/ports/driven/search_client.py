"""What the crawler expects from any client that searches; its errors are in ``client_errors``."""

from abc import ABC, abstractmethod

from p2pwatch.domain.identifiers import Channel
from p2pwatch.domain.search.answer import SearchAnswer


class SearchClient(ABC):
    """Searches a keyword on one of its channels."""

    @abstractmethod
    def channels(self) -> tuple[Channel, ...]:
        """The channels it searches: opaque names the core never tests."""

    @abstractmethod
    async def search(self, keyword: str, channel: Channel, budget_seconds: float) -> SearchAnswer:
        """Returns once the client signals the end, or ``budget_seconds`` after the search's
        network start at the latest."""
