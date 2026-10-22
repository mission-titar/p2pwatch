"""``ConfigChecker`` over ``load_config``: the YAML files read as the crawl reads them."""

from collections.abc import Mapping
from pathlib import Path, PurePath

from p2pwatch.adapters.driven.config.crawler_config import load_config
from p2pwatch.application.ports.driven.config_checker import ConfigChecker


class FilesystemConfigChecker(ConfigChecker):
    """Loads the three files, ``${NAME}`` interpolated from ``env``, and keeps nothing."""

    def __init__(self, env: Mapping[str, str]) -> None:
        self._env = env

    def check_config(
        self, *, config_path: PurePath, targets_path: PurePath, matcher_path: PurePath
    ) -> None:
        load_config(Path(config_path), Path(targets_path), Path(matcher_path), self._env)
