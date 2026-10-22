"""``ConfigValidator``: validates a node's config without starting anything."""

from abc import ABC, abstractmethod
from pathlib import PurePath


class ConfigValidator(ABC):
    """Validates the three config files as the crawl would load them."""

    @abstractmethod
    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        """Returns when the config is valid; raises ``InvalidConfigError`` otherwise."""
