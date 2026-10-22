from p2pwatch.adapters.driven.random_jitter_generator import RandomJitterGenerator


def test_random_jitter_generator_jitter_is_within_span() -> None:
    jitter_generator = RandomJitterGenerator(jitter_seed=42)
    for _ in range(20):
        jitter = jitter_generator.jitter(10.0)
        assert 0.0 <= jitter < 10.0


def test_random_jitter_generator_jitter_is_reproducible_for_a_seed() -> None:
    a = [RandomJitterGenerator(jitter_seed=7).jitter(5.0) for _ in range(3)]
    b = [RandomJitterGenerator(jitter_seed=7).jitter(5.0) for _ in range(3)]
    assert a == b  # same jitter_seed → same sequence of draws


def test_random_jitter_generator_jitter_zero_or_negative_span_is_zero() -> None:
    jitter_generator = RandomJitterGenerator(jitter_seed=1)
    assert jitter_generator.jitter(0.0) == 0.0
    assert jitter_generator.jitter(-3.0) == 0.0
