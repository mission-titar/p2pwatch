"""``CrawlerRunner``: runs the crawler a node's config describes, until it is stopped."""

from abc import ABC, abstractmethod
from pathlib import PurePath


class CrawlerRunner(ABC):
    """Crawls with the three config files, until a signal or the webui stops it."""

    @abstractmethod
    async def run_crawler(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        """Raises ``InvalidConfigError`` on a refused config, ``OutOfSpaceError`` short of disk
        space for a database's opening, ``HeldDatabaseError`` for a database another process
        holds, ``ShutdownDeadlineError`` once the shutdown deadline fired."""
