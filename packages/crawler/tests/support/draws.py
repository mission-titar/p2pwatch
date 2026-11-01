"""The draws of a contract's wide values from the test's ``randomness``: a text, a quantity and an
instant, which a value's draw keeps apart from its other fields of the same type."""

from datetime import UTC, datetime, timedelta
from random import Random

# Wide but well formed: ASCII's printable characters but "{", which only a JSON text holds, letters
# with a case and an accent, other scripts, and characters beyond U+FFFF.
_ALPHABET = "".join(
    [
        *(chr(code_point) for code_point in range(0x20, 0x7F) if chr(code_point) != "{"),
        "àÀçÇéÉèÈêÊïÏôÔœŒùÙüÜßñÑ",
        "ΣσςЖж",
        "ケロ軍曹",
        "\N{FROG FACE}\N{GRINNING FACE}",
    ]
)
# A value's quantities each take a residue of their own modulo this, so no two are equal.
_RESIDUES = 8
_QUANTITY_STEPS = 2**56
_EARLIEST = datetime(1970, 1, 1, tzinfo=UTC)
_SPAN_MICROS = timedelta(days=36525) // timedelta(microseconds=1)


def draw_text(randomness: Random, *, lengths: range) -> str:
    """A text of a length drawn from ``lengths``, holding no ``{``."""
    return "".join(randomness.choices(_ALPHABET, k=randomness.choice(lengths)))


def draw_quantity(randomness: Random, *, residue: int) -> int:
    """A quantity congruent to ``residue`` modulo 8."""
    return draw_quantities(randomness, residue=residue, count=1)[0]


def draw_quantities(randomness: Random, *, residue: int, count: int) -> tuple[int, ...]:
    """``count`` distinct quantities, ascending, each congruent to ``residue`` modulo 8."""
    steps = sorted(randomness.sample(range(_QUANTITY_STEPS), count))
    return tuple(step * _RESIDUES + residue for step in steps)


def draw_instant(randomness: Random) -> datetime:
    """A UTC instant to the microsecond, in the century from the Unix epoch."""
    return draw_instants(randomness, count=1)[0]


def draw_instants(randomness: Random, *, count: int) -> tuple[datetime, ...]:
    """``count`` distinct instants, ascending, as ``draw_instant`` draws them."""
    offsets_micros = sorted(randomness.sample(range(_SPAN_MICROS), count))
    return tuple(_EARLIEST + timedelta(microseconds=micros) for micros in offsets_micros)
