from datetime import timedelta
from random import Random

from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.support.domain.search.backoff import draw_backoff_key, draw_backoff_state

_SEEDS = range(1000)


def test_a_drawn_key_holds_a_channel_or_the_whole_client() -> None:
    randomness = Random(0)
    assert draw_backoff_key(randomness, has_channel=True).channel is not None
    assert draw_backoff_key(randomness, has_channel=False).channel is None


def test_a_drawn_key_keeps_the_client_its_test_relates() -> None:
    randomness = Random(0)
    whole_client = draw_backoff_key(randomness, has_channel=False)
    channel = draw_backoff_key(randomness, has_channel=True, client_name=whole_client.client_name)
    assert channel.client_name == whole_client.client_name


def test_a_drawn_state_counts_at_least_one_attempt() -> None:
    assert all(1 <= draw_backoff_state(Random(seed)).attempts < 2**63 for seed in _SEEDS)


def test_a_drawn_delay_survives_a_round_trip_through_float_seconds() -> None:
    for seed in _SEEDS:
        delay = draw_backoff_state(Random(seed)).delay
        assert timedelta(0) <= delay
        assert timedelta(seconds=delay.total_seconds()) == delay


def test_drawn_delays_reach_the_microsecond() -> None:
    assert any(draw_backoff_state(Random(seed)).delay.microseconds % 1000 for seed in _SEEDS)


def test_the_same_seed_draws_the_same_backoff() -> None:
    def drawn(randomness: Random) -> tuple[BackoffKey, BackoffKey, BackoffState]:
        return (
            draw_backoff_key(randomness, has_channel=True),
            draw_backoff_key(randomness, has_channel=False),
            draw_backoff_state(randomness),
        )

    assert drawn(Random("a test's node id")) == drawn(Random("a test's node id"))
