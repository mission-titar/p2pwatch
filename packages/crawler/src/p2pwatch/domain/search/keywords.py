"""Deduplication of the search keywords from config (PURE, spec search-simplification).

PURE domain: no I/O. Keywords are provided by config (``crawler.yml``,
``search.keywords``): by default ``keroro`` (wide net) + ``titar`` (FR sentinel,
jackpot-proof). ``dedupe_keywords`` is deterministic: same list → same tuple, ORDERED
and DEDUPLICATED (first seen wins).
"""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchKeyword:
    """A keyword to search. FROZEN and hashable → trivial deduplication."""

    text: str


def dedupe_keywords(keywords: Sequence[str]) -> tuple[SearchKeyword, ...]:
    """ORDERED and DEDUPLICATED list of keywords (spec search-simplification).

    Order = input order; deduplication by ``text`` (first seen wins); empty strings are
    ignored.
    """
    seen: set[str] = set()
    result: list[SearchKeyword] = []
    for text in keywords:
        if text and text not in seen:
            seen.add(text)
            result.append(SearchKeyword(text=text))
    return tuple(result)
