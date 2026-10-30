"""The backoff every worker shares: each key's wait grows, resets, and survives a restart."""

import dataclasses
from datetime import timedelta

from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_time import FakeTime

_KAD = BackoffKey(client_name=ClientName("amule-1"), channel=Channel("kad"))
_ED2K = BackoffKey(client_name=ClientName("amule-1"), channel=Channel("ed2k"))

# jitter_ratio 0.0 + FakeJitterGenerator(jitter_value=0.0) → backoff = exact NOMINAL delay.
_POLICY = BackoffPolicy(
    base_seconds=2.0,
    cap_seconds=60.0,
    factor=2.0,
    jitter_ratio=0.0,
)


def _registry(
    fake_time: FakeTime, saved: dict[BackoffKey, BackoffState] | None = None
) -> BackoffRegistry:
    backoff_state_store = FakeBackoffStateStore()
    backoff_state_store.set_backoff_states(saved or {})
    return BackoffRegistry(
        _POLICY,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        jitter_generator=FakeJitterGenerator(),
        backoff_state_reader=backoff_state_store,
    )


def test_backoff_registry_grows_then_resets() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    assert registry.record_failure(_KAD) == timedelta(seconds=2)  # 1st attempt = base
    fake_time.advance(timedelta(seconds=2.0))
    assert registry.record_failure(_KAD) == timedelta(seconds=4)  # × factor
    registry.reset(_KAD)
    assert registry.record_failure(_KAD) == timedelta(seconds=2)  # back to base


def test_a_failure_while_backed_off_does_not_count_again() -> None:
    # Concurrent searches started before a backoff fail together: one round, one attempt.
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.advance(timedelta(seconds=0.5))
    # what is left of the backoff already set
    assert registry.record_failure(_KAD) == timedelta(seconds=1.5)
    fake_time.advance(timedelta(seconds=1.5))
    assert registry.record_failure(_KAD) == timedelta(seconds=4)  # the second attempt


def test_backoff_registry_keys_are_independent() -> None:
    registry = _registry(FakeTime())
    assert registry.record_failure(_KAD) == timedelta(seconds=2)
    assert registry.record_failure(_ED2K) == timedelta(seconds=2)  # not kad's counter


def test_backoff_registry_reset_unknown_key_is_a_noop() -> None:
    _registry(FakeTime()).reset(_KAD)  # does not raise


def test_a_failure_backs_its_key_off_for_its_delay() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=1.9))  # still before its delay (2.0s)
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=0.1))
    assert registry.is_in_backoff(_KAD) is False


def test_a_wall_clock_step_forward_keeps_the_key_backed_off() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.step_wall(timedelta(hours=1))
    assert registry.is_in_backoff(_KAD) is True


def test_a_wall_clock_step_back_releases_the_key_at_its_delay() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    fake_time.step_wall(timedelta(hours=-1))
    fake_time.advance(timedelta(seconds=1.9))
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=0.1))
    assert registry.is_in_backoff(_KAD) is False


def test_backoff_registry_unknown_key_is_not_in_backoff() -> None:
    assert _registry(FakeTime()).is_in_backoff(_KAD) is False


def test_backoff_registry_jitter_extends_the_delay() -> None:
    fake_time = FakeTime()
    policy = dataclasses.replace(_POLICY, jitter_ratio=0.5)  # jitter in [0, 0.5*delay)
    jitter_generator = FakeJitterGenerator(jitter_value=1.0)  # constant 1.0s jitter
    registry = BackoffRegistry(
        policy,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        jitter_generator=jitter_generator,
        backoff_state_reader=FakeBackoffStateStore(),
    )
    delay = registry.record_failure(_KAD)
    assert delay == timedelta(seconds=3)  # base 2.0 + jitter 1.0
    assert jitter_generator.jitter_spans == [1.0]  # span = jitter_ratio (0.5) * delay (2.0)


def test_the_snapshot_holds_each_waits_start_on_the_wall_clock_and_its_delay() -> None:
    fake_time = FakeTime()
    registry = _registry(fake_time)
    registry.record_failure(_KAD)
    started_at = fake_time.wall.now()
    fake_time.advance(timedelta(seconds=1))
    assert registry.snapshot() == {
        _KAD: BackoffState(attempts=1, started_at=started_at, delay=timedelta(seconds=2))
    }


def test_a_resumed_backoff_waits_what_is_left_of_its_delay() -> None:
    fake_time = FakeTime()
    started_at = fake_time.wall.now() - timedelta(seconds=100)
    saved = {_KAD: BackoffState(attempts=1, started_at=started_at, delay=timedelta(seconds=300))}
    registry = _registry(fake_time, saved)
    registry.resume_waits()
    assert registry.snapshot() == saved
    assert registry.time_until_retry(_KAD) == timedelta(seconds=200)


def test_a_resumed_backoff_started_in_the_future_waits_its_delay_at_most() -> None:
    fake_time = FakeTime()
    started_at = fake_time.wall.now() + timedelta(hours=1)
    registry = _registry(
        fake_time,
        {_KAD: BackoffState(attempts=1, started_at=started_at, delay=timedelta(seconds=300))},
    )
    registry.resume_waits()
    fake_time.advance(timedelta(seconds=299))
    assert registry.is_in_backoff(_KAD) is True
    fake_time.advance(timedelta(seconds=1))
    assert registry.is_in_backoff(_KAD) is False


def test_a_resumed_backoff_keeps_its_attempts() -> None:
    fake_time = FakeTime()
    started_at = fake_time.wall.now() - timedelta(hours=1)
    registry = _registry(
        fake_time,
        {_KAD: BackoffState(attempts=2, started_at=started_at, delay=timedelta(seconds=4))},
    )
    registry.resume_waits()
    assert registry.is_in_backoff(_KAD) is False
    assert registry.record_failure(_KAD) == timedelta(seconds=8)  # the third attempt
