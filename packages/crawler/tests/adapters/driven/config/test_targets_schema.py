from pathlib import PurePath
from typing import Any

import pytest

from p2pwatch.adapters.driven.config.targets_schema import targets_from_document
from p2pwatch.domain.invalid_config import InvalidConfigError
from p2pwatch.domain.matching.models import TargetSegment

_FILE = PurePath("/srv/targets.yml")


def _episode(**keys: object) -> dict[str, Any]:
    """Episode 62 and its one segment, ``keys`` replacing or adding the episode's."""
    return {
        "season": 2,
        "seasonal_number": 11,
        "absolute_number": 62,
        "segments": [{"letter": "A", "title": "x"}],
    } | keys


def _segment_episode(**keys: object) -> dict[str, Any]:
    """Episode 62 and its one segment, ``keys`` replacing or adding the segment's."""
    return _episode(segments=[{"letter": "A", "title": "x"} | keys])


def _problems(document: dict[str, Any]) -> list[tuple[str | None, str]]:
    """The key and message of each problem of ``document``, all of them in ``_FILE``."""
    with pytest.raises(InvalidConfigError) as raised:
        targets_from_document(document, file_path=_FILE)
    assert {problem.file_path for problem in raised.value.problems} == {_FILE}
    return [(problem.key, problem.message) for problem in raised.value.problems]


def test_a_document_gives_a_target_per_segment_its_status_lost_by_default() -> None:
    document = {
        "episodes": [
            _episode(
                segments=[
                    {"letter": "A", "title": "Les demoiselles", "status": "found"},
                    {"letter": "B", "title": "Le grand combat"},
                ]
            ),
            _episode(season=1, seasonal_number=10, absolute_number=10),
        ]
    }
    episode_62 = {"season": 2, "seasonal_number": 11, "absolute_number": 62}
    assert targets_from_document(document, file_path=_FILE) == (
        TargetSegment(**episode_62, letter="A", title="Les demoiselles", status="found"),
        TargetSegment(**episode_62, letter="B", title="Le grand combat", status="lost"),
        TargetSegment(season=1, seasonal_number=10, absolute_number=10, letter="A", title="x"),
    )


def test_an_episode_without_segments_gives_no_target() -> None:
    episode = _episode()
    del episode["segments"]
    assert targets_from_document({"episodes": [episode]}, file_path=_FILE) == ()


def test_a_letter_beyond_ascii_that_is_no_control_character_is_accepted() -> None:
    document = {"episodes": [_segment_episode(letter="\xe9\xa0")]}
    [target] = targets_from_document(document, file_path=_FILE)
    assert target.letter == "\xe9\xa0"


@pytest.mark.parametrize(
    ("document", "key", "message"),
    [
        ({}, "episodes", "Field required"),
        ({"episodes": "nope"}, "episodes", "Input should be a valid list"),
        ({"episodes": ["nope"]}, "episodes[0]", "Input should be a valid dictionary"),
        (
            {"episodes": [_episode(segments={"letter": "A"})]},
            "episodes[0].segments",
            "Input should be a valid list",
        ),
        (
            {"episodes": [_episode(segments=["A"])]},
            "episodes[0].segments[0]",
            "Input should be a valid dictionary",
        ),
    ],
)
def test_a_level_of_the_wrong_shape_is_refused(
    *, document: dict[str, Any], key: str, message: str
) -> None:
    assert _problems(document) == [(key, message)]


@pytest.mark.parametrize("key", ["season", "seasonal_number", "absolute_number"])
def test_an_episode_number_absent_is_required(key: str) -> None:
    episode = _episode()
    del episode[key]
    assert _problems({"episodes": [episode]}) == [(f"episodes[0].{key}", "Field required")]


# Strict: neither a float, even whole, nor a numeric string, nor a boolean is converted.
@pytest.mark.parametrize("number", [2.7, 62.0, "62", True, None, [1]])
@pytest.mark.parametrize("key", ["season", "seasonal_number", "absolute_number"])
def test_an_episode_number_is_an_integer(*, key: str, number: object) -> None:
    assert _problems({"episodes": [_episode(**{key: number})]}) == [
        (f"episodes[0].{key}", "Input should be a valid integer")
    ]


@pytest.mark.parametrize("key", ["letter", "title"])
def test_a_segment_text_absent_is_required(key: str) -> None:
    episode = _episode()
    del episode["segments"][0][key]
    assert _problems({"episodes": [episode]}) == [
        (f"episodes[0].segments[0].{key}", "Field required")
    ]


@pytest.mark.parametrize("text", [1984, 2.5, None])
@pytest.mark.parametrize("key", ["letter", "title"])
def test_a_segment_text_is_a_string(*, key: str, text: object) -> None:
    assert _problems({"episodes": [_segment_episode(**{key: text})]}) == [
        (f"episodes[0].segments[0].{key}", "Input should be a valid string")
    ]


@pytest.mark.parametrize("status", ["complete", "partial", "", "LOST"])
def test_a_status_outside_the_closed_set_is_refused(status: str) -> None:
    assert _problems({"episodes": [_segment_episode(status=status)]}) == [
        ("episodes[0].segments[0].status", "Input should be 'lost' or 'found'")
    ]


# Cc: the C0 controls, DEL and the C1 controls.
@pytest.mark.parametrize("letter", ["a\x1fb", "\x85", "\x00", "\x7f", "a\tb"])
def test_a_control_character_in_a_letter_is_refused_without_its_value(letter: str) -> None:
    assert _problems({"episodes": [_segment_episode(letter=letter)]}) == [
        ("episodes[0].segments[0].letter", "holds a control character")
    ]


@pytest.mark.parametrize(
    ("document", "key"),
    [
        ({"episodes": [], "serie": "Keroro"}, "serie"),
        ({"episodes": [_episode(name="Keroro")]}, "episodes[0].name"),
        (
            {"episodes": [_segment_episode(broadcast_date="2008-01-01")]},
            "episodes[0].segments[0].broadcast_date",
        ),
    ],
    ids=["file", "episode", "segment"],
)
def test_a_key_nothing_reads_is_refused_at_each_level(
    *, document: dict[str, Any], key: str
) -> None:
    assert _problems(document) == [(key, "Extra inputs are not permitted")]


def test_every_problem_of_the_file_is_listed() -> None:
    document = {
        "episodes": [
            _episode(season=2.7, segments=[{"letter": "A", "title": 1984, "status": "done"}]),
            _episode(absolute_number="63", segments=[{"title": "y"}]),
        ]
    }
    assert [key for key, _ in _problems(document)] == [
        "episodes[0].season",
        "episodes[0].segments[0].title",
        "episodes[0].segments[0].status",
        "episodes[1].absolute_number",
        "episodes[1].segments[0].letter",
    ]


def test_every_duplicate_target_is_listed_naming_its_first_holder() -> None:
    document = {
        "episodes": [
            _episode(segments=[{"letter": "a", "title": "x"}, {"letter": "A", "title": "y"}]),
            _episode(season=1, absolute_number=10),
            _episode(season=2, segments=[{"letter": "A", "title": "z"}]),
            _episode(season=1, absolute_number=10),
        ]
    }
    assert _problems(document) == [
        (
            "episodes[0].segments[1]",
            "same target_id as episodes[0].segments[0], letters compared upper-cased",
        ),
        (
            "episodes[2].segments[0]",
            "same target_id as episodes[0].segments[0], letters compared upper-cased",
        ),
        (
            "episodes[3].segments[0]",
            "same target_id as episodes[1].segments[0], letters compared upper-cased",
        ),
    ]


def test_the_duplicates_wait_for_the_file_to_hold() -> None:
    document = {"episodes": [_episode(), _episode(season="2")]}
    assert _problems(document) == [("episodes[1].season", "Input should be a valid integer")]


def test_no_message_prints_the_value_received() -> None:
    secret = "s3cr3t-value"
    document = {"episodes": [_segment_episode(letter=f"{secret}\x00", note=secret), secret]}
    problems = _problems(document)
    assert len(problems) == 3
    assert not [message for _, message in problems if secret in message]
