"""``CrawlResumer``: resumes a paused crawl."""

from abc import ABC, abstractmethod


class CrawlResumer(ABC):
    """Resumes a paused crawl, from any thread."""

    @abstractmethod
    def resume_crawl(self) -> None:
        """Returns at once: the crawler searches again."""
