from pathlib import PurePath
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError, create_model

from p2pwatch.adapters.driven.config.validation_problems import (
    moved_key,
    removed_key,
    validation_problems,
)
from p2pwatch.domain.config_problem import ConfigProblem

_FILE = PurePath("/srv/crawler.yml")


class _Fields(BaseModel, extra="forbid", strict=True):
    count: int = 0


def _problems(document: dict[str, Any]) -> tuple[ConfigProblem, ...]:
    # Built in the test: a type made at import is credited to none of the module's own tests.
    refused: dict[str, Any] = {
        "old_count": (removed_key("crawler.yml"), None),
        "total": (moved_key("section.total", file_name="crawler.yml"), None),
    }
    with pytest.raises(ValidationError) as raised:
        create_model("Document", __base__=_Fields, **refused).model_validate(document)
    return validation_problems(raised.value, file_path=_FILE)


def _problem(key: str, *, message: str) -> ConfigProblem:
    return ConfigProblem(file_path=_FILE, key=key, message=message)


def test_each_error_is_a_problem_of_the_file_named_by_its_key() -> None:
    assert _problems({"count": "2", "unread": True}) == (
        _problem("count", message="Input should be a valid integer"),
        _problem("unread", message="Extra inputs are not permitted"),
    )


def test_a_removed_key_is_refused_even_empty() -> None:
    assert _problems({"old_count": None}) == (
        _problem("old_count", message="was removed, delete it from crawler.yml"),
    )


def test_a_moved_key_is_refused_with_its_new_place() -> None:
    assert _problems({"total": 3}) == (
        _problem("total", message="moved to 'section.total', move it in crawler.yml"),
    )


def test_no_message_prints_the_value_received() -> None:
    problems = _problems({"count": "SECRET", "unread": "SECRET"})
    assert [problem.key for problem in problems] == ["count", "unread"]
    assert all("SECRET" not in problem.message for problem in problems)
