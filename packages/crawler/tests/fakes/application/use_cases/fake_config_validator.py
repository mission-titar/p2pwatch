from pathlib import PurePath

from p2pwatch.application.ports.driving.config_validator import ConfigValidator
from p2pwatch.domain.invalid_config import InvalidConfigError


class FakeConfigValidator(ConfigValidator):
    """Records the paths of each validation, and raises ``refusal`` when given one."""

    def __init__(self, refusal: InvalidConfigError | None = None) -> None:
        self.validated_paths: list[tuple[PurePath, PurePath, PurePath]] = []
        self._refusal = refusal

    def validate_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        self.validated_paths.append((config_path, targets_path, matcher_path))
        if self._refusal is not None:
            raise self._refusal
