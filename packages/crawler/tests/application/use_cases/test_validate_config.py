"""``ValidateConfig``: hands the three paths to the config checker, and its refusal back."""

from pathlib import PurePath

import pytest

from p2pwatch.application.ports.driven.config_checker import ConfigChecker
from p2pwatch.application.use_cases.validate_config import ValidateConfig
from p2pwatch.domain.invalid_config import InvalidConfigError

_CONFIG_PATH = PurePath("deploy/crawler.yml")
_TARGETS_PATH = PurePath("deploy/targets.yml")
_MATCHER_PATH = PurePath("deploy/matcher.yml")


class _FakeConfigChecker(ConfigChecker):
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


def test_validate_config_checks_each_path_once_in_its_role() -> None:
    config_checker = _FakeConfigChecker()

    ValidateConfig(config_checker).validate_config(
        config_path=_CONFIG_PATH, targets_path=_TARGETS_PATH, matcher_path=_MATCHER_PATH
    )

    assert config_checker.checked_paths == [(_CONFIG_PATH, _TARGETS_PATH, _MATCHER_PATH)]


def test_an_invalid_config_raises_the_checkers_refusal() -> None:
    refusal = InvalidConfigError("'episodes' section: list expected")

    with pytest.raises(InvalidConfigError) as raised:
        ValidateConfig(_FakeConfigChecker(refusal)).validate_config(
            config_path=_CONFIG_PATH, targets_path=_TARGETS_PATH, matcher_path=_MATCHER_PATH
        )

    assert raised.value is refusal
