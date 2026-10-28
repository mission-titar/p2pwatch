from p2pwatch.domain.identifiers import Keyword
from p2pwatch.domain.search.keywords import dedupe_keywords


def test_generates_one_keyword_per_input_in_order() -> None:
    assert dedupe_keywords(["keroro", "titar"]) == (Keyword("keroro"), Keyword("titar"))


def test_deduplicates_keeping_first_seen_order() -> None:
    keywords = dedupe_keywords(["keroro", "titar", "keroro"])
    assert keywords == (Keyword("keroro"), Keyword("titar"))


def test_drops_empty_strings() -> None:
    assert dedupe_keywords(["", "keroro"]) == (Keyword("keroro"),)


def test_empty_input_yields_empty_tuple() -> None:
    assert dedupe_keywords([]) == ()
