from pathlib import PurePath

from p2pwatch.application.ports.driving.config_validator import ConfigReport, ConfigValidator

_NO_PROBLEM = ConfigReport(problems=())


class FakeConfigValidator(ConfigValidator):
    """Records the paths of each validation, and returns ``config_report``."""

    def __init__(self, config_report: ConfigReport = _NO_PROBLEM) -> None:
        self.validated_paths: list[tuple[PurePath, PurePath, PurePath]] = []
        self._config_report = config_report

    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> ConfigReport:
        self.validated_paths.append((config_path, targets_path, matcher_path))
        return self._config_report
