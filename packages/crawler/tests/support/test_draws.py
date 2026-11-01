from datetime import UTC, timedelta
from random import Random

from tests.support.draws import (
    draw_instant,
    draw_instants,
    draw_quantities,
    draw_quantity,
    draw_text,
)

_SEEDS = range(1000)


def test_a_drawn_text_is_at_least_8_characters_long() -> None:
    assert min(len(draw_text(Random(seed))) for seed in _SEEDS) == 8


def test_drawn_texts_reach_beyond_ascii() -> None:
    assert any(not draw_text(Random(seed)).isascii() for seed in _SEEDS)


def test_drawn_quantities_are_distinct_ascending_quantities() -> None:
    for seed in _SEEDS:
        quantities = draw_quantities(Random(seed), count=4)
        assert list(quantities) == sorted(set(quantities))
        assert len(quantities) == 4
        assert all(0 <= quantity < 2**63 for quantity in quantities)


def test_drawn_instants_are_distinct_ascending_and_in_utc() -> None:
    for seed in _SEEDS:
        instants = draw_instants(Random(seed), count=3)
        assert list(instants) == sorted(set(instants))
        assert len(instants) == 3
        assert {instant.utcoffset() for instant in instants} == {timedelta(0)}
        assert all(instant.tzinfo is UTC for instant in instants)


def test_drawn_instants_reach_the_microsecond() -> None:
    assert any(draw_instant(Random(seed)).microsecond % 1000 for seed in _SEEDS)


def test_the_same_seed_draws_the_same_values() -> None:
    def draws(randomness: Random) -> tuple[object, ...]:
        return (
            draw_text(randomness),
            draw_quantity(randomness),
            draw_quantities(randomness, count=2),
            draw_instant(randomness),
            draw_instants(randomness, count=2),
        )

    assert draws(Random("a test's node id")) == draws(Random("a test's node id"))
