"""``YamlConfigChecker``: loads the three files as the crawl does, interpolated from its env."""

from pathlib import Path, PurePath

import pytest

from p2pwatch.adapters.config.yaml_config_checker import YamlConfigChecker
from p2pwatch.domain.invalid_config import InvalidConfigError

_DEPLOY = Path(__file__).resolve().parents[5] / "deploy"


def _check_shipped_config(config_checker: YamlConfigChecker) -> None:
    config_checker.check_config(
        config_path=PurePath(_DEPLOY / "crawler.yml"),
        targets_path=PurePath(_DEPLOY / "targets.yml"),
        matcher_path=PurePath(_DEPLOY / "matcher.yml"),
    )


def test_the_shipped_config_passes_with_its_password_in_the_env() -> None:
    _check_shipped_config(YamlConfigChecker({"AMULE_API_PASSWORD": "s3cr3t"}))


def test_a_variable_missing_from_the_env_given_is_an_invalid_config() -> None:
    with pytest.raises(InvalidConfigError, match="'AMULE_API_PASSWORD'"):
        _check_shipped_config(YamlConfigChecker({}))
