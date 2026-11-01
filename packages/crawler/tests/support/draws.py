"""The draws of a contract's wide values from the test's ``randomness``: a text, a quantity and an
instant, each at random over a wide range."""

from datetime import UTC, datetime, timedelta
from random import Random

# Wide but well formed: ASCII's printable characters, letters with a case and an accent, other
# scripts, and characters beyond U+FFFF.
_ALPHABET = "".join(
    [
        *map(chr, range(0x20, 0x7F)),
        "àÀçÇéÉèÈêÊïÏôÔœŒùÙüÜßñÑ",
        "ΣσςЖж",
        "ケロ軍曹",
        "\N{FROG FACE}\N{GRINNING FACE}",
    ]
)
_TEXT_LENGTHS = range(8, 65)
_QUANTITY_END = 2**62
_EARLIEST = datetime(1970, 1, 1, tzinfo=UTC)
_SPAN_MICROS = timedelta(days=36525) // timedelta(microseconds=1)


def draw_text(randomness: Random) -> str:
    """A text of 8 to 64 characters."""
    return "".join(randomness.choices(_ALPHABET, k=randomness.choice(_TEXT_LENGTHS)))


def draw_quantity(randomness: Random) -> int:
    """A quantity below 2**62."""
    return draw_quantities(randomness, count=1)[0]


def draw_quantities(randomness: Random, *, count: int) -> tuple[int, ...]:
    """``count`` distinct quantities, ascending, as ``draw_quantity`` draws them."""
    return tuple(sorted(randomness.sample(range(_QUANTITY_END), count)))


def draw_instant(randomness: Random) -> datetime:
    """A UTC instant to the microsecond, in the century from the Unix epoch."""
    return draw_instants(randomness, count=1)[0]


def draw_instants(randomness: Random, *, count: int) -> tuple[datetime, ...]:
    """``count`` distinct instants, ascending, as ``draw_instant`` draws them."""
    offsets_micros = sorted(randomness.sample(range(_SPAN_MICROS), count))
    return tuple(_EARLIEST + timedelta(microseconds=micros) for micros in offsets_micros)
