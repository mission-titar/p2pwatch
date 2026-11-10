"""What a store's contract needs to have its storage refuse a write."""

from random import Random
from typing import Protocol

# More than a page of storage holds: a write of it needs room a full storage has not left.
_LONG_TEXT_LENGTH = 1 << 16


class RefuseWrites(Protocol):
    """Makes the store's storage refuse every write from then on, full or read-only."""

    def __call__(self) -> None: ...


def draw_long_text(randomness: Random) -> str:
    """A text of 64 Ki characters."""
    return "".join(randomness.choices("abcdefghijklmnopqrstuvwxyz", k=_LONG_TEXT_LENGTH))
