"""``CrawlPauser``: pauses the crawl."""

from abc import ABC, abstractmethod


class CrawlPauser(ABC):
    """Pauses the crawl, from any thread."""

    @abstractmethod
    def pause_crawl(self) -> None:
        """Returns at once: searches in flight finish, then the crawler idles."""
