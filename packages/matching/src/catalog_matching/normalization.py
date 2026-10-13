"""String normalization for matching (cf. spec §8.1)."""

import unicodedata

# French ligatures (œ, æ) are not decomposed by NFKD and not folded to ASCII by
# casefold. Table deliberately limited to the targeted FR/DE corpus (§8.1): this
# is NOT the exhaustive list of Unicode letters in this situation (e.g. ĳ, ĸ
# survive too).
_LIGATURES = {"œ": "oe", "æ": "ae"}


def fold(value: str) -> str:
    """NFKD -> strip combining diacritics -> casefold -> ligatures; punctuation and digits KEPT.

    Used by ``regex`` tokens (so ``teletoon``/``fevrier`` match without accent classes, and
    ``°`` stays for ``n°062a``), and first step of :func:`normalize` (cf. spec §8.1).
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    folded = without_marks.casefold()
    for ligature, replacement in _LIGATURES.items():
        folded = folded.replace(ligature, replacement)
    return folded


def normalize(value: str) -> str:
    """Fold a string for keyword/coverage matching (cf. spec §8.1).

    ``fold`` -> non-alphanumerics turned into spaces -> spaces collapsed -> trim.
    """
    folded = fold(value)
    cleaned = "".join(ch if ch.isalnum() else " " for ch in folded)
    return " ".join(cleaned.split())


def split_words(value: str) -> list[str]:
    """The words of a string, after normalization."""
    return normalize(value).split()
