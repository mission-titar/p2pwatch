"""``ConfigChecker``: reads and parses a node's config files, keeping nothing."""

from abc import ABC, abstractmethod
from pathlib import PurePath

from p2pwatch.domain.config_problem import ConfigProblem


class ConfigChecker(ABC):
    """Checks each config file, read and parsed as the crawl reads it, and returns its problems:
    none when it is valid, a file it cannot read being one with no key."""

    @abstractmethod
    def check_crawler_config(self, config_path: PurePath) -> tuple[ConfigProblem, ...]:
        """``crawler.yml``'s problems, its ``${NAME}`` resolved."""

    @abstractmethod
    def check_targets(self, targets_path: PurePath) -> tuple[ConfigProblem, ...]:
        """``targets.yml``'s problems."""

    @abstractmethod
    def check_matcher_config(self, matcher_path: PurePath) -> tuple[ConfigProblem, ...]:
        """``matcher.yml``'s problems."""
