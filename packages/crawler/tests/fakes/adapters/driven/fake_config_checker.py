from pathlib import PurePath

from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.domain.invalid_config import InvalidConfigError


class FakeConfigChecker(ConfigChecker):
    """Records the paths of each check, and raises ``refusal`` when given one."""

    def __init__(self, refusal: InvalidConfigError | None = None) -> None:
        self.checked_paths: list[tuple[PurePath, PurePath, PurePath]] = []
        self._refusal = refusal

    def check_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        self.checked_paths.append((config_path, targets_path, matcher_path))
        if self._refusal is not None:
            raise self._refusal
