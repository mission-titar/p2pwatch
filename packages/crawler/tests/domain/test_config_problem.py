import pytest

from p2pwatch.domain.config_problem import key_path


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ((), ""),
        (("amule_api_password",), "amule_api_password"),
        (("search", "keywords", 0), "search.keywords[0]"),
        (("matrix", 0, 1, "cell"), "matrix[0][1].cell"),
        (("tokens", "1"), "tokens.1"),
    ],
)
def test_a_key_path_joins_keys_by_dots_and_puts_indexes_in_brackets(
    *, parts: tuple[str | int, ...], expected: str
) -> None:
    assert key_path(*parts) == expected


def test_a_key_path_escapes_each_character_a_terminal_would_not_print() -> None:
    assert key_path("a\x1fb", "\N{ZERO WIDTH SPACE}é") == "a\\x1fb.\\u200bé"
