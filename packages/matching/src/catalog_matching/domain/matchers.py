"""Leaf matchers of the matching engine (cf. spec §8.2)."""

import re
from collections.abc import Mapping
from typing import Protocol

from rapidfuzz import fuzz

from catalog_matching.domain.combinators import Matcher
from catalog_matching.domain.models import FileCandidate
from catalog_matching.domain.normalization import fold, split_words


class KeywordMatcher(Matcher):
    """True if the phrase's words are a CONTIGUOUS subsequence of the filename's words."""

    def __init__(self, phrase: str) -> None:
        self._phrase_words = split_words(phrase)

    def matches(self, candidate: FileCandidate) -> bool:
        needle = self._phrase_words
        haystack = split_words(candidate.filename)
        if not needle:
            return True
        # Sliding window of width len(needle): CONTIGUOUS subsequence.
        last_start = len(haystack) - len(needle)
        return any(
            haystack[start : start + len(needle)] == needle for start in range(last_start + 1)
        )


class RegexMatcher(Matcher):
    """Regex match on ``fold(filename)``. If ``"i"`` in ``flags``, prefixes ``(?i)``.

    Patterns are compiled with ``re.ASCII`` so ``\\b \\d \\s \\w`` keep ASCII semantics
    (matching the prior RE2 default), which is what the existing policy relies on.

    We explicitly prefix ``(?i)`` to the pattern rather than passing a flag constant.

    ``flags`` is a short ``re``-style string: ``"i"`` enables case-insensitivity,
    ``""`` leaves it case-sensitive. Expected values from the YAML config (Plan 2b):
    ``"i"`` or ``""``. Detection is ``"i" in flags``: do not pass verbose names
    (``"ignore_case"``…), which would enable ``(?i)`` by accident. An invalid pattern
    raises ``re.error`` at construction (config validation delegated to Plan 2b).
    """

    def __init__(self, pattern: str, *, flags: str = "i") -> None:
        if "i" in flags:
            pattern = "(?i)" + pattern
        self._compiled = re.compile(pattern, re.ASCII)

    def matches(self, candidate: FileCandidate) -> bool:
        return self._compiled.search(fold(candidate.filename)) is not None


# French stopwords (already folded by split_words) excluded from the significant words
# of a CoverageMatcher's reference (cf. spec §8.2: R = words(title) \ stopwords).
# Deliberately minimal set: under-filtering favors recall (better to keep a borderline
# word than to drop a significant one).
STOPWORDS_FR: frozenset[str] = frozenset(
    {
        "le",
        "la",
        "les",
        "l",
        "de",
        "des",
        "du",
        "d",
        "un",
        "une",
        "et",
        "a",
        "au",
        "aux",
        "en",
    }
)


class CoverageMatcher(Matcher):
    """Fuzzy fraction of ``reference``'s significant words that are covered (cf. spec §8.2)."""

    def __init__(
        self, reference: str, *, min_coverage: float, min_similarity: float = 0.85
    ) -> None:
        self._reference_words = [t for t in split_words(reference) if t not in STOPWORDS_FR]
        self._min_coverage = min_coverage
        self._min_similarity = min_similarity

    def coverage(self, candidate: FileCandidate) -> float:
        reference_words = self._reference_words
        if not reference_words:
            return 0.0
        filename_words = split_words(candidate.filename)
        covered_word_count = sum(
            1
            for reference_word in reference_words
            if any(
                fuzz.ratio(reference_word, filename_word) / 100 >= self._min_similarity
                for filename_word in filename_words
            )
        )
        return covered_word_count / len(reference_words)

    def matches(self, candidate: FileCandidate) -> bool:
        return self.coverage(candidate) >= self._min_coverage


class AttributeExtractor(Protocol):
    def __call__(self, candidate: FileCandidate, /) -> float | None: ...


# The closed set of FileCandidate numeric attributes attr_between reads (cf. spec §8.2).
READERS_BY_ATTR: Mapping[str, AttributeExtractor] = {
    "size_mib": lambda candidate: candidate.size_mib,
    "duration_seconds": lambda candidate: candidate.duration_seconds,
    "bitrate_kbps": lambda candidate: candidate.bitrate_kbps,
}


class AttributeBetweenMatcher(Matcher):
    """True if the numeric attribute is PRESENT and within ``[min_bound, max_bound]`` (§8.2).

    Open bounds when ``min_bound``/``max_bound`` are ``None``. Missing attribute -> false.
    """

    def __init__(
        self,
        attr: str,
        *,
        min_bound: float | None = None,
        max_bound: float | None = None,
    ) -> None:
        if attr not in READERS_BY_ATTR:
            raise ValueError(
                f"unknown attribute: {attr!r} (expected one of {sorted(READERS_BY_ATTR)})"
            )
        self._read_attr = READERS_BY_ATTR[attr]
        self._min_bound = min_bound
        self._max_bound = max_bound

    def matches(self, candidate: FileCandidate) -> bool:
        attribute = self._read_attr(candidate)
        return (
            attribute is not None
            and (self._min_bound is None or attribute >= self._min_bound)
            and (self._max_bound is None or attribute <= self._max_bound)
        )
