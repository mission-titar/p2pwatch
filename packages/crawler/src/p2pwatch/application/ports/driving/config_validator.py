"""``ConfigValidator``: validates a node's config without starting anything."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath

from p2pwatch.domain.config_problem import ConfigProblem


@dataclass(kw_only=True, frozen=True)
class ConfigReport:
    """The problems of a config, every file's in the crawl's order: none when it is valid."""

    problems: tuple[ConfigProblem, ...]


class ConfigValidator(ABC):
    """Validates the three config files as the crawl would load them."""

    @abstractmethod
    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> ConfigReport:
        """The config's report, a file it cannot read being one of its problems."""
