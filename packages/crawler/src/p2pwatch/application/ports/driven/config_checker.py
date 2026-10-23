"""``ConfigChecker``: reads and parses a node's config files, keeping nothing."""

from abc import ABC, abstractmethod
from pathlib import PurePath


class ConfigChecker(ABC):
    """Checks each config file, read and parsed as the crawl reads it: a wrong content raises
    ``InvalidConfigError``, a file it cannot read ``BrokenInputError``."""

    @abstractmethod
    def check_crawler_config(self, config_path: PurePath) -> None:
        """Returns when ``crawler.yml`` parses, its ``${NAME}`` resolved."""

    @abstractmethod
    def check_targets(self, targets_path: PurePath) -> None:
        """Returns when ``targets.yml`` parses."""

    @abstractmethod
    def check_matcher_config(self, matcher_path: PurePath) -> None:
        """Returns when ``matcher.yml`` parses."""
