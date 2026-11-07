"""``ConfigChecker`` over the reads of ``crawler_config``: each file read as the crawl reads it."""

from collections.abc import Mapping
from pathlib import Path, PurePath

from p2pwatch.adapters.driven.config.crawler_config import (
    FileRead,
    read_crawler_config,
    read_matcher_config,
    read_targets,
)
from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.domain.config_problem import ConfigProblem
from p2pwatch.domain.invalid_config import InvalidConfigError


class FilesystemConfigChecker(ConfigChecker):
    """Reads each file, ``crawler.yml``'s ``${NAME}`` resolved from ``env``, and keeps nothing."""

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env

    def check_crawler_config(self, config_path: PurePath) -> tuple[ConfigProblem, ...]:
        return _problems_of(read=lambda: read_crawler_config(Path(config_path), env=self._env))

    def check_targets(self, targets_path: PurePath) -> tuple[ConfigProblem, ...]:
        return _problems_of(read=lambda: read_targets(Path(targets_path)))

    def check_matcher_config(self, matcher_path: PurePath) -> tuple[ConfigProblem, ...]:
        return _problems_of(read=lambda: read_matcher_config(Path(matcher_path)))


def _problems_of(*, read: FileRead[object]) -> tuple[ConfigProblem, ...]:
    """The problems of ``read``'s file, none when it returns."""
    try:
        read()
    except InvalidConfigError as error:
        return error.problems
    return ()
