"""``ValidateConfig``: checks each file in its role, and reports the first wrong one."""

from pathlib import PurePath

import pytest

from p2pwatch.application.ports.driving.config_validator import ConfigProblem, ConfigReport
from p2pwatch.application.use_cases.validate_config import ValidateConfig
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.invalid_config import InvalidConfigError
from tests.fakes.adapters.driven.fake_config_checker import FakeConfigChecker

_CONFIG_PATH = PurePath("deploy/crawler.yml")
_TARGETS_PATH = PurePath("deploy/targets.yml")
_MATCHER_PATH = PurePath("deploy/matcher.yml")


def _validate(config_checker: FakeConfigChecker) -> ConfigReport:
    return ValidateConfig(config_checker).validate_config(
        config_path=_CONFIG_PATH, targets_path=_TARGETS_PATH, matcher_path=_MATCHER_PATH
    )


def test_a_valid_config_reports_no_problem_once_each_file_is_checked_in_its_role() -> None:
    config_checker = FakeConfigChecker()

    assert _validate(config_checker) == ConfigReport(problems=())

    assert config_checker.checked_files == [
        ("crawler_config", _CONFIG_PATH),
        ("targets", _TARGETS_PATH),
        ("matcher_config", _MATCHER_PATH),
    ]


def test_a_wrong_key_is_reported_with_its_file_and_its_key() -> None:
    refusal = InvalidConfigError("search.keywords", message="non-empty list of strings expected")

    config_report = _validate(FakeConfigChecker({_CONFIG_PATH: refusal}))

    assert config_report == ConfigReport(
        problems=(
            ConfigProblem(
                file_path=_CONFIG_PATH,
                key="search.keywords",
                message="non-empty list of strings expected",
            ),
        )
    )


def test_the_first_wrong_file_is_the_only_one_reported_and_checked_last() -> None:
    refusal = InvalidConfigError(None, message="'episodes' section: list expected")
    config_checker = FakeConfigChecker({_TARGETS_PATH: refusal})

    config_report = _validate(config_checker)

    assert config_report == ConfigReport(
        problems=(
            ConfigProblem(
                file_path=_TARGETS_PATH, key=None, message="'episodes' section: list expected"
            ),
        )
    )
    assert [path for _, path in config_checker.checked_files] == [_CONFIG_PATH, _TARGETS_PATH]


def test_a_broken_file_raises_instead_of_being_reported() -> None:
    broken_input = BrokenInputError(f"{_MATCHER_PATH}: No such file or directory")

    with pytest.raises(BrokenInputError) as raised:
        _validate(FakeConfigChecker({_MATCHER_PATH: broken_input}))

    assert raised.value is broken_input
