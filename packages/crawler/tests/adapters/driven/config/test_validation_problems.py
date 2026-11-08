from pathlib import PurePath
from typing import Annotated, Any

import pytest
from pydantic import (
    AfterValidator,
    BaseModel,
    Discriminator,
    Field,
    Tag,
    ValidationError,
    create_model,
)

from p2pwatch.adapters.driven.config.validation_problems import (
    TAG_MARK,
    moved_key,
    refuse_control_character,
    removed_key,
    renamed_key,
    validation_problems,
)
from p2pwatch.domain.config_problem import ConfigProblem

_FILE = PurePath("/srv/crawler.yml")


class _Section(BaseModel, extra="forbid", strict=True):
    total: int
    counts: list[int] = Field(default_factory=list)


class _Fields(BaseModel, extra="forbid", strict=True):
    count: int = 0
    section: _Section = Field(default_factory=lambda: _Section(total=0))


def _problems(document: dict[str, Any]) -> tuple[ConfigProblem, ...]:
    # Built in the test: a type made at import is credited to none of the module's own tests.
    renamed: dict[str, Any] = {"sum": (renamed_key("total", file_name="crawler.yml"), None)}
    section = create_model("Section", __base__=_Section, **renamed)
    refused: dict[str, Any] = {
        "old_count": (removed_key("crawler.yml"), None),
        "total": (moved_key("section.total", file_name="crawler.yml"), None),
        "section": (section, Field(default_factory=lambda: section(total=0))),
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


def test_a_key_under_a_mapping_or_a_list_is_named_by_its_path() -> None:
    assert _problems({"section": {"total": 1, "counts": [1, "2"]}}) == (
        _problem("section.counts[1]", message="Input should be a valid integer"),
    )


def test_a_mapping_expected_names_no_class_of_the_schema() -> None:
    assert _problems({"section": "SECRET"}) == (
        _problem("section", message="Input should be a valid dictionary"),
    )


def test_a_removed_key_is_refused_even_empty() -> None:
    assert _problems({"old_count": None}) == (
        _problem("old_count", message="was removed, delete it from crawler.yml"),
    )


def test_a_moved_key_is_one_problem_its_new_place_not_required_beside_it() -> None:
    assert _problems({"section": {}, "total": 3}) == (
        _problem("total", message="moved to 'section.total', move it in crawler.yml"),
    )


def test_the_new_place_of_a_moved_key_is_required_without_it() -> None:
    assert _problems({"section": {}}) == (_problem("section.total", message="Field required"),)


def test_a_renamed_key_is_one_problem_its_new_name_not_required_beside_it() -> None:
    assert _problems({"section": {"sum": 3}}) == (
        _problem("section.sum", message="was renamed 'total', rename it in crawler.yml"),
    )


def test_no_message_prints_the_value_received() -> None:
    problems = _problems({"count": "SECRET", "unread": "SECRET"})
    assert [problem.key for problem in problems] == ["count", "unread"]
    assert all("SECRET" not in problem.message for problem in problems)


class _Circle(BaseModel, extra="forbid", strict=True):
    radius: int


class _Square(BaseModel, extra="forbid", strict=True):
    side: int


def _shape(value: object) -> str:
    return (
        f"{TAG_MARK}circle"
        if isinstance(value, dict) and "radius" in value
        else f"{TAG_MARK}square"
    )


class _Drawing(BaseModel, extra="forbid", strict=True):
    shape: Annotated[
        Annotated[_Circle, Tag(f"{TAG_MARK}circle")] | Annotated[_Square, Tag(f"{TAG_MARK}square")],
        Discriminator(_shape),
    ]


def test_a_tagged_union_s_tag_is_no_part_of_a_key_path() -> None:
    with pytest.raises(ValidationError) as raised:
        _Drawing.model_validate({"shape": {"radius": "2"}})
    assert validation_problems(raised.value, file_path=_FILE) == (
        _problem("shape.radius", message="Input should be a valid integer"),
    )


class _Named(BaseModel, extra="forbid", strict=True):
    name: Annotated[str, AfterValidator(refuse_control_character)]


# Cc: the C0 controls, DEL and the C1 controls.
@pytest.mark.parametrize("name", ["a\x1fb", "\x85", "\x7f"])
def test_a_text_holding_a_control_character_is_refused(name: str) -> None:
    with pytest.raises(ValidationError) as raised:
        _Named.model_validate({"name": name})
    assert validation_problems(raised.value, file_path=_FILE) == (
        _problem("name", message="holds a control character"),
    )


# A zero width space is a format character, no control character.
@pytest.mark.parametrize("name", ["\xe9\xa0", "\N{ZERO WIDTH SPACE}"])
def test_a_text_beyond_ascii_that_holds_no_control_character_is_accepted(name: str) -> None:
    assert _Named.model_validate({"name": name}).name == name
