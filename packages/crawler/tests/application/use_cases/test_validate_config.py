"""``ValidateConfig``: checks each file in its role, and reports every problem of every file."""

from pathlib import PurePath

from p2pwatch.application.ports.driving.config_validator import ConfigReport
from p2pwatch.application.use_cases.validate_config import ValidateConfig
from p2pwatch.domain.config_problem import ConfigProblem
from tests.fakes.adapters.driven.fake_config_checker import FakeConfigChecker

_CONFIG_PATH = PurePath("deploy/crawler.yml")
_TARGETS_PATH = PurePath("deploy/targets.yml")
_MATCHER_PATH = PurePath("deploy/matcher.yml")


def _validate(config_checker: FakeConfigChecker) -> ConfigReport:
    return ValidateConfig(config_checker).validate_config(
        config_path=_CONFIG_PATH, targets_path=_TARGETS_PATH, matcher_path=_MATCHER_PATH
    )


def _problem(file_path: PurePath, *, key: str | None) -> ConfigProblem:
    return ConfigProblem(file_path=file_path, key=key, message="list expected")


def test_a_valid_config_reports_no_problem_once_each_file_is_checked_in_its_role() -> None:
    config_checker = FakeConfigChecker()

    assert _validate(config_checker) == ConfigReport(problems=())

    assert config_checker.checked_files == [
        ("crawler_config", _CONFIG_PATH),
        ("targets", _TARGETS_PATH),
        ("matcher_config", _MATCHER_PATH),
    ]


def test_every_problem_of_every_file_is_reported_in_the_files_order() -> None:
    crawler_problems = (
        _problem(_CONFIG_PATH, key="search.keywords"),
        _problem(_CONFIG_PATH, key=None),
    )
    matcher_problem = _problem(_MATCHER_PATH, key=None)
    config_checker = FakeConfigChecker(
        {_MATCHER_PATH: (matcher_problem,), _CONFIG_PATH: crawler_problems}
    )

    config_report = _validate(config_checker)

    assert config_report == ConfigReport(problems=(*crawler_problems, matcher_problem))
    assert [path for _, path in config_checker.checked_files] == [
        _CONFIG_PATH,
        _TARGETS_PATH,
        _MATCHER_PATH,
    ]
