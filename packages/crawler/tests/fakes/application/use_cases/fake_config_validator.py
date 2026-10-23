from pathlib import PurePath

from p2pwatch.application.ports.driving.config_validator import ConfigReport, ConfigValidator
from p2pwatch.domain.broken_input_error import BrokenInputError

_NO_PROBLEM = ConfigReport(problems=())


class FakeConfigValidator(ConfigValidator):
    """Records the paths of each validation, and returns ``outcome``, or raises it when broken."""

    def __init__(self, outcome: ConfigReport | BrokenInputError = _NO_PROBLEM) -> None:
        self.validated_paths: list[tuple[PurePath, PurePath, PurePath]] = []
        self._outcome = outcome

    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> ConfigReport:
        self.validated_paths.append((config_path, targets_path, matcher_path))
        if isinstance(self._outcome, BrokenInputError):
            raise self._outcome
        return self._outcome
