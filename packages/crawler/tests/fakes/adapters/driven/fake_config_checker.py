from pathlib import PurePath

from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.invalid_config import InvalidConfigError


class FakeConfigChecker(ConfigChecker):
    """Records each check with its file's role, and raises the refusal given for its path."""

    def __init__(
        self, refusals_by_path: dict[PurePath, InvalidConfigError | BrokenInputError] | None = None
    ) -> None:
        self.checked_files: list[tuple[str, PurePath]] = []
        self._refusals_by_path = refusals_by_path or {}

    def check_crawler_config(self, config_path: PurePath) -> None:
        self._check("crawler_config", path=config_path)

    def check_targets(self, targets_path: PurePath) -> None:
        self._check("targets", path=targets_path)

    def check_matcher_config(self, matcher_path: PurePath) -> None:
        self._check("matcher_config", path=matcher_path)

    def _check(self, role: str, *, path: PurePath) -> None:
        self.checked_files.append((role, path))
        if path in self._refusals_by_path:
            raise self._refusals_by_path[path]
