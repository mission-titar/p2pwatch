"""``FilesystemConfigChecker``: reads each file as the crawl does, ``crawler.yml`` from its env."""

from pathlib import Path, PurePath
from typing import Protocol

import pytest

from p2pwatch.adapters.driven.config.filesystem_config_checker import FilesystemConfigChecker
from p2pwatch.domain.config_problem import ConfigProblem

_DEPLOY = Path(__file__).resolve().parents[6] / "deploy"
_ENV = {"AMULE_API_PASSWORD": "s3cr3t"}


class ConfigCheck(Protocol):
    def __call__(self, path: PurePath, /) -> tuple[ConfigProblem, ...]: ...


def test_the_shipped_files_have_no_problem_with_the_password_in_the_env() -> None:
    config_checker = FilesystemConfigChecker(_ENV)

    assert config_checker.check_crawler_config(PurePath(_DEPLOY / "crawler.yml")) == ()
    assert config_checker.check_targets(PurePath(_DEPLOY / "targets.yml")) == ()
    assert config_checker.check_matcher_config(PurePath(_DEPLOY / "matcher.yml")) == ()


def test_a_variable_missing_from_the_env_given_is_a_problem_naming_its_key() -> None:
    path = PurePath(_DEPLOY / "crawler.yml")

    [problem] = FilesystemConfigChecker({}).check_crawler_config(path)

    assert (problem.file_path, problem.key) == (path, "amule_api_password")


@pytest.mark.parametrize(
    ("check", "text", "key", "message"),
    [
        (
            FilesystemConfigChecker(_ENV).check_targets,
            "episodes: nope\n",
            "episodes",
            "Input should be a valid list",
        ),
        (
            FilesystemConfigChecker(_ENV).check_matcher_config,
            "rules: {}\n",
            None,
            "'rules' section: ",
        ),
    ],
    ids=["targets", "matcher"],
)
def test_a_wrong_policy_file_is_a_problem_of_it(
    *,
    tmp_path: Path,
    check: ConfigCheck,
    text: str,
    key: str | None,
    message: str,
) -> None:
    path = tmp_path / "policy.yml"
    path.write_text(text, encoding="utf-8")

    [problem] = check(PurePath(path))

    assert (problem.file_path, problem.key) == (path, key)
    assert problem.message.startswith(message)


@pytest.mark.parametrize(
    "check",
    [
        FilesystemConfigChecker(_ENV).check_crawler_config,
        FilesystemConfigChecker(_ENV).check_targets,
        FilesystemConfigChecker(_ENV).check_matcher_config,
    ],
    ids=["crawler", "targets", "matcher"],
)
def test_an_absent_file_is_one_problem_of_it_naming_no_key(
    *, tmp_path: Path, check: ConfigCheck
) -> None:
    path = PurePath(tmp_path / "absent.yml")

    assert check(path) == (
        ConfigProblem(file_path=path, key=None, message="No such file or directory"),
    )


def test_a_file_that_is_not_yaml_is_one_problem_of_it(tmp_path: Path) -> None:
    path = tmp_path / "targets.yml"
    path.write_text("episodes: [1, 2\n", encoding="utf-8")

    [problem] = FilesystemConfigChecker(_ENV).check_targets(PurePath(path))

    assert (problem.file_path, problem.key) == (path, None)
    assert problem.message.startswith("invalid YAML: ")
