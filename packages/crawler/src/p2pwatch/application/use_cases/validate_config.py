"""Validates a node's config by checking its three files, starting nothing."""

from pathlib import PurePath

from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.application.ports.driving.config_validator import ConfigReport, ConfigValidator


class ValidateConfig(ConfigValidator):
    """Checks every file in the crawl's order and reports the problems of all of them."""

    def __init__(self, config_checker: ConfigChecker) -> None:
        self._config_checker = config_checker

    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> ConfigReport:
        return ConfigReport(
            problems=(
                *self._config_checker.check_crawler_config(config_path),
                *self._config_checker.check_targets(targets_path),
                *self._config_checker.check_matcher_config(matcher_path),
            )
        )
