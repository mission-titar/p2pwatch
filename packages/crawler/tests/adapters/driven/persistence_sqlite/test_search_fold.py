import pytest

from p2pwatch.adapters.driven.persistence_sqlite.search_fold import fold_for_search


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("ÉCOLE", "ecole"),
        ("Ça Keroro", "ca keroro"),
        ("e\N{COMBINING ACUTE ACCENT}cole", "ecole"),
        ("Straße", "strasse"),
        ("50% a_b a\\b", "50% a_b a\\b"),
    ],
    ids=["capitals with accents", "cedilla", "accent already split", "casefold", "symbols kept"],
)
def test_a_text_is_folded_to_its_case_folded_letters_without_their_accents(
    *, text: str, folded: str
) -> None:
    assert fold_for_search(text) == folded


def test_none_is_folded_to_none() -> None:
    assert fold_for_search(None) is None
