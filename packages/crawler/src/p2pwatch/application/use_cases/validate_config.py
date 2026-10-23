"""Validates a node's config by checking its three files, starting nothing."""

from pathlib import PurePath

from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.application.ports.driving.config_validator import (
    ConfigProblem,
    ConfigReport,
    ConfigValidator,
)
from p2pwatch.domain.invalid_config import InvalidConfigError


class ValidateConfig(ConfigValidator):
    """Checks each file in the crawl's order and reports the first wrong one."""

    def __init__(self, config_checker: ConfigChecker) -> None:
        self._config_checker = config_checker

    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> ConfigReport:
        checks = (
            (config_path, self._config_checker.check_crawler_config),
            (targets_path, self._config_checker.check_targets),
            (matcher_path, self._config_checker.check_matcher_config),
        )
        for file_path, check in checks:
            try:
                check(file_path)
            except InvalidConfigError as error:
                return ConfigReport(problems=(ConfigProblem(file_path, error.key, error.message),))
        return ConfigReport(problems=())
