"""``fold_for_search``, the SQL function a reader's search compares the text and a name through."""

from catalog_matching.domain.normalization import fold


def fold_for_search(text: str | None) -> str | None:
    """The matcher's ``fold`` of ``text``: casefolded, without accents or ligatures; ``None`` for
    ``None``."""
    return None if text is None else fold(text)
