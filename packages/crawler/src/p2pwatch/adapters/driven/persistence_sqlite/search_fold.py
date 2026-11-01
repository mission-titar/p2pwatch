"""``fold_for_search``, the SQL function a reader's search compares the text and a name through."""

import unicodedata


def fold_for_search(text: str | None) -> str | None:
    """``text`` casefolded, decomposed (NFD) and stripped of its combining marks, its accents;
    ``None`` for ``None``."""
    if text is None:
        return None
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))
