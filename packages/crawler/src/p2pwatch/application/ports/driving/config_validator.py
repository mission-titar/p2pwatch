"""``ConfigValidator``: validates a node's config without starting anything."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import PurePath


@dataclass(kw_only=True, frozen=True)
class ConfigProblem:
    """What a config file holds wrong: ``key`` is the key path it names, ``None`` for none."""

    file_path: PurePath
    key: str | None
    message: str


@dataclass(kw_only=True, frozen=True)
class ConfigReport:
    """The problems of a config: at most one, the parse stopping at the first."""

    problems: tuple[ConfigProblem, ...]


class ConfigValidator(ABC):
    """Validates the three config files as the crawl would load them."""

    @abstractmethod
    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> ConfigReport:
        """The config's report; raises ``BrokenInputError`` on a file it cannot read."""
