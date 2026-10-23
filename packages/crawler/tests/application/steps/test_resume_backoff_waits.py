"""The search backoff a previous run saved holds its waits again: what is left of each."""

from datetime import timedelta

from p2pwatch.application.steps.resume_backoff_waits import resume_backoff_waits
from p2pwatch.application.steps.search_worker import BackoffPolicy, BackoffRegistry
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_time import FakeTime

_KAD = BackoffKey("amuled", "kad")
_POLICY = BackoffPolicy(base_seconds=2.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0)


def test_a_saved_wait_resumes_with_what_is_left_of_it() -> None:
    fake_time = FakeTime()
    started_at = fake_time.wall.now() - timedelta(seconds=100)
    saved = {_KAD: BackoffState(1, started_at, timedelta(seconds=300))}
    backoff_state_store = FakeBackoffStateStore()
    backoff_state_store.set_backoff_states(saved)
    backoff = BackoffRegistry(_POLICY, fake_time.wall, fake_time.monotonic, FakeJitterGenerator())

    resume_backoff_waits(backoff, backoff_state_store)

    assert backoff.snapshot() == saved
    assert backoff.time_until_retry(_KAD) == timedelta(seconds=200)
