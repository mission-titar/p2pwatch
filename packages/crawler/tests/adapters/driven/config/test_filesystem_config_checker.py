"""``FilesystemConfigChecker``: reads each file as the crawl does, ``crawler.yml`` from its env."""

from collections.abc import Callable
from pathlib import Path, PurePath

import pytest

from p2pwatch.adapters.driven.config.filesystem_config_checker import FilesystemConfigChecker
from p2pwatch.domain.broken_input_error import BrokenInputError
from p2pwatch.domain.invalid_config import InvalidConfigError

_DEPLOY = Path(__file__).resolve().parents[6] / "deploy"
_ENV = {"AMULE_API_PASSWORD": "s3cr3t"}


def test_the_shipped_files_pass_with_the_password_in_the_env() -> None:
    config_checker = FilesystemConfigChecker(_ENV)

    config_checker.check_crawler_config(PurePath(_DEPLOY / "crawler.yml"))
    config_checker.check_targets(PurePath(_DEPLOY / "targets.yml"))
    config_checker.check_matcher_config(PurePath(_DEPLOY / "matcher.yml"))


def test_a_variable_missing_from_the_env_given_is_an_invalid_config_naming_its_key() -> None:
    with pytest.raises(InvalidConfigError) as raised:
        FilesystemConfigChecker({}).check_crawler_config(PurePath(_DEPLOY / "crawler.yml"))

    assert raised.value.key == "amule_api_password"


@pytest.mark.parametrize(
    ("check", "text", "message"),
    [
        (FilesystemConfigChecker.check_targets, "episodes: nope\n", "'episodes' section: "),
        (FilesystemConfigChecker.check_matcher_config, "rules: {}\n", "'rules' section: "),
    ],
    ids=["targets", "matcher"],
)
def test_a_wrong_policy_file_is_an_invalid_config_naming_no_key_apart(
    tmp_path: Path,
    check: Callable[[FilesystemConfigChecker, PurePath], None],
    text: str,
    message: str,
) -> None:
    path = tmp_path / "policy.yml"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(InvalidConfigError) as raised:
        check(FilesystemConfigChecker(_ENV), PurePath(path))

    assert raised.value.key is None
    assert raised.value.message.startswith(message)


@pytest.mark.parametrize(
    "check",
    [
        FilesystemConfigChecker.check_crawler_config,
        FilesystemConfigChecker.check_targets,
        FilesystemConfigChecker.check_matcher_config,
    ],
    ids=["crawler", "targets", "matcher"],
)
def test_an_absent_file_is_a_broken_input_naming_it(
    tmp_path: Path, check: Callable[[FilesystemConfigChecker, PurePath], None]
) -> None:
    path = PurePath(tmp_path / "absent.yml")

    with pytest.raises(BrokenInputError, match=f"^{path}: No such file or directory$"):
        check(FilesystemConfigChecker(_ENV), path)
