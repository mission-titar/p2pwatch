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


def test_a_drawn_text_takes_its_length_from_its_range_and_holds_no_brace() -> None:
    texts = [draw_text(Random(seed), lengths=range(3, 5)) for seed in _SEEDS]
    assert {len(text) for text in texts} == {3, 4}
    assert not any("{" in text for text in texts)


def test_drawn_texts_reach_beyond_ascii() -> None:
    assert any(
        not text.isascii()
        for text in (draw_text(Random(seed), lengths=range(8, 9)) for seed in _SEEDS)
    )


def test_drawn_quantities_are_distinct_ascending_and_of_their_residue() -> None:
    for seed in _SEEDS:
        quantities = draw_quantities(Random(seed), residue=3, count=4)
        assert list(quantities) == sorted(set(quantities))
        assert len(quantities) == 4
        assert {quantity % 8 for quantity in quantities} == {3}
        assert all(0 <= quantity < 2**63 for quantity in quantities)


def test_a_drawn_quantity_is_of_its_residue() -> None:
    assert {draw_quantity(Random(seed), residue=5) % 8 for seed in _SEEDS} == {5}


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
            draw_text(randomness, lengths=range(1, 50)),
            draw_quantity(randomness, residue=0),
            draw_quantities(randomness, residue=1, count=2),
            draw_instant(randomness),
            draw_instants(randomness, count=2),
        )

    assert draws(Random("a test's node id")) == draws(Random("a test's node id"))
