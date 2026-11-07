from pathlib import PurePath

from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.domain.config_problem import ConfigProblem


class FakeConfigChecker(ConfigChecker):
    """Records each check with its file's role, and returns the problems given for its path."""

    def __init__(
        self, problems_by_path: dict[PurePath, tuple[ConfigProblem, ...]] | None = None
    ) -> None:
        self.checked_files: list[tuple[str, PurePath]] = []
        self._problems_by_path = problems_by_path or {}

    def check_crawler_config(self, config_path: PurePath) -> tuple[ConfigProblem, ...]:
        return self._check("crawler_config", path=config_path)

    def check_targets(self, targets_path: PurePath) -> tuple[ConfigProblem, ...]:
        return self._check("targets", path=targets_path)

    def check_matcher_config(self, matcher_path: PurePath) -> tuple[ConfigProblem, ...]:
        return self._check("matcher_config", path=matcher_path)

    def _check(self, role: str, *, path: PurePath) -> tuple[ConfigProblem, ...]:
        self.checked_files.append((role, path))
        return self._problems_by_path.get(path, ())
