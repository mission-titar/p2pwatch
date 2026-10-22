"""Validates a node's config by checking its three files, starting nothing."""

from pathlib import PurePath

from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.application.ports.driving.config_validator import ConfigValidator


class ValidateConfig(ConfigValidator):
    """The config is valid when its checker accepts the three files."""

    def __init__(self, config_checker: ConfigChecker) -> None:
        self._config_checker = config_checker

    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        self._config_checker.check_config(
            config_path=config_path, targets_path=targets_path, matcher_path=matcher_path
        )
