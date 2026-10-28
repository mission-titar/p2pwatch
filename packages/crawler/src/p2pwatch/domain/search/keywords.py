"""Deduplication of the search keywords from config (PURE, spec search-simplification).

PURE domain: no I/O. Keywords are provided by config (``crawler.yml``,
``search.keywords``): by default ``keroro`` (wide net) + ``titar`` (FR sentinel,
jackpot-proof). ``dedupe_keywords`` is deterministic: same list → same tuple, ORDERED
and DEDUPLICATED (first seen wins).
"""

from collections.abc import Sequence

from p2pwatch.domain.identifiers import Keyword


def dedupe_keywords(keywords: Sequence[str]) -> tuple[Keyword, ...]:
    """ORDERED and DEDUPLICATED list of keywords (spec search-simplification).

    Order = input order; deduplication first seen wins; empty strings are ignored.
    """
    seen: set[str] = set()
    deduplicated: list[Keyword] = []
    for text in keywords:
        if text and text not in seen:
            seen.add(text)
            deduplicated.append(Keyword(text))
    return tuple(deduplicated)
