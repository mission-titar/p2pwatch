"""The backoff the searches share, saved after each turn that changed it (stage 2, D7)."""

from datetime import timedelta

from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_time import FakeTime

_KAD = BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad"))
_POLICY = BackoffPolicy(base_seconds=60.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0)


class _Saving:
    """A saver over a registry and a store sharing one fake timeline."""

    def __init__(self) -> None:
        self.fake_time = FakeTime()
        self.state = FakeBackoffStateStore()
        self.backoff = BackoffRegistry(
            _POLICY,
            wall_clock=self.fake_time.wall,
            monotonic_clock=self.fake_time.monotonic,
            jitter_generator=FakeJitterGenerator(),
            backoff_state_reader=self.state,
        )
        self.logger = FakeLogger()
        self.saver = BackoffSaver(
            backoff=self.backoff, backoff_state_writer=self.state, logger=self.logger
        )

    def failed_turn(self) -> None:
        with self.saver.saving():
            self.backoff.record_failure(_KAD)

    def succeeded_turn(self) -> None:
        with self.saver.saving():
            self.backoff.reset(_KAD)


def test_the_backoff_is_saved_after_each_turn_that_changed_it() -> None:
    saving = _Saving()

    saving.failed_turn()
    saving.failed_turn()  # within its wait: the same round, nothing changed
    saving.succeeded_turn()
    saving.succeeded_turn()

    assert [set(saved) for saved in saving.state.saved] == [{_KAD}, set()]


def test_the_backoff_resumed_after_the_saver_was_built_is_not_saved_again() -> None:
    saving = _Saving()
    resumed = {
        _KAD: BackoffState(
            attempts=1, started_at=saving.fake_time.wall.now(), delay=timedelta(seconds=60)
        )
    }
    saving.state.set_backoff_states(resumed)  # the previous run's save
    saving.backoff.resume_waits()

    with saving.saver.saving():
        pass

    assert saving.state.saved == [resumed]


def test_a_failed_save_is_logged_and_retried_after_the_next_turn() -> None:
    saving = _Saving()
    saving.state.failures = 1

    saving.failed_turn()
    saving.fake_time.advance(timedelta(seconds=60))
    saving.failed_turn()

    assert saving.logger.lines == [
        LoggedLine(
            level="error",
            message="backoff not saved (database is locked): retried after the next search",
        )
    ]
    assert [saved[_KAD].attempts for saved in saving.state.saved] == [2]
