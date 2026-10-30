"""The bounds of the values the node stores: well-formed text and quantities. PURE domain."""

import re

# Half of a UTF-16 pair, which no UTF-8 text holds.
_SURROGATES = re.compile(r"[\ud800-\udfff]")

# SQLite's INTEGER, a signed 64-bit integer, holds every quantity below it.
_QUANTITY_END = 2**63


def require_well_formed_text(text: str | None, *, error_label: str) -> None:
    """Refuses ``text`` unless well formed: valid UTF-8, so holding no surrogate, paired or not,
    since a pair left in a ``str`` fails every sink a lone one does. ``None`` passes."""
    if text is not None and _SURROGATES.search(text):
        raise ValueError(f"{error_label} is not valid UTF-8")


def require_quantity(quantity: int | None, *, error_label: str) -> None:
    """Refuses ``quantity`` unless it is one: an integer in [0, 2**63), since no count nor size is
    negative and the catalog's ``INTEGER`` holds none larger. ``None`` passes."""
    if quantity is not None and not 0 <= quantity < _QUANTITY_END:
        raise ValueError(f"{error_label} is not a quantity in [0, 2**63): {quantity}")
