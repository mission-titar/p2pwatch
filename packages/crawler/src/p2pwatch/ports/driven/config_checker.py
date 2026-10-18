"""``ConfigChecker``: loads and parses a node's config files, keeping nothing."""

from abc import ABC, abstractmethod
from pathlib import PurePath


class ConfigChecker(ABC):
    """Checks the three config files, each read and parsed as the crawl reads it."""

    @abstractmethod
    def check_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        """Returns when every file loads and parses; raises ``InvalidConfigError`` otherwise."""
