import dataclasses

import pytest

from p2pwatch.domain.json_object_text import JsonObjectText
from tests.support.domain.value_bounds import NOT_WELL_FORMED_TEXTS, WELL_FORMED_TEXTS

# A nesting json.loads cannot parse: it raises RecursionError past about 10 000 levels.
_TOO_DEEP = '{"a": ' + "[" * 10_000 + "]" * 10_000 + "}"


def test_from_object_writes_its_keys_sorted_at_every_level() -> None:
    json_object_text = JsonObjectText.from_object({"b": (1, None), "a": {"d": True, "c": "é"}})

    assert json_object_text.text == '{"a": {"c": "é", "d": true}, "b": [1, null]}'


@pytest.mark.parametrize("text", WELL_FORMED_TEXTS)
def test_a_canonical_text_is_kept_as_it_is_and_compares_by_its_text(text: str) -> None:
    canonical = f'{{"a": [-1.5, "{text}", null, false], "b": {{}}}}'

    json_object_text = JsonObjectText(text=canonical)

    assert json_object_text.text == canonical
    assert json_object_text == JsonObjectText.from_object({"b": {}, "a": [-1.5, text, None, False]})
    with pytest.raises(dataclasses.FrozenInstanceError):
        json_object_text.text = "{}"  # type: ignore[misc]


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_from_object_refuses_a_number_that_is_not_finite(number: float) -> None:
    with pytest.raises(ValueError, match="^a JSON text holds a number that is not finite$"):
        JsonObjectText.from_object({"a": number})


@pytest.mark.parametrize("text", NOT_WELL_FORMED_TEXTS)
@pytest.mark.parametrize(
    "position", ["name", "text", "text in a list", "text in an object", "nested name"]
)
def test_from_object_refuses_text_that_is_not_valid_utf8(*, position: str, text: str) -> None:
    json_object_by_position: dict[str, dict[str, object]] = {
        "name": {text: 1},
        "text": {"a": text},
        "text in a list": {"a": ["b", text]},
        "text in an object": {"a": {"b": text}},
        "nested name": {"a": {text: "b"}},
    }

    with pytest.raises(ValueError, match="^a JSON text is not valid UTF-8$"):
        JsonObjectText.from_object(json_object_by_position[position])


def test_from_object_refuses_a_nested_object_whose_names_sort_as_numbers() -> None:
    with pytest.raises(ValueError, match="^a JSON text is not in its canonical form$"):
        JsonObjectText.from_object({"a": {2: "b", 10: "c"}})


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("not json", "does not parse"),
        ("", "does not parse"),
        (_TOO_DEEP, "does not parse"),
        ("[]", "is not an object"),
        ('"a"', "is not an object"),
        ("null", "is not an object"),
        ('{"a": NaN}', "holds a number that is not finite"),
        ('{"a": 1e999}', "holds a number that is not finite"),
        ('{"a": -Infinity}', "holds a number that is not finite"),
        ('{"b": 1, "a": 2}', "is not in its canonical form"),
        ('{"a": 1, "a": 1}', "is not in its canonical form"),
        ('{"a":1}', "is not in its canonical form"),
        (" {}", "is not in its canonical form"),
        ('{"a": "\\u00e9"}', "is not in its canonical form"),
        ('{"a": 1.0e0}', "is not in its canonical form"),
        ('{"a": "\\ud800"}', "is not in its canonical form"),
        ('{"\\udc80": 1}', "is not in its canonical form"),
    ],
)
def test_a_text_that_is_not_the_canonical_text_of_an_object_is_refused(
    *, text: str, problem: str
) -> None:
    with pytest.raises(ValueError, match=f"^a JSON text {problem}$"):
        JsonObjectText(text=text)
