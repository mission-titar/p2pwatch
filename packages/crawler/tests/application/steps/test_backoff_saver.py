"""The backoff every search shares is saved after each search that changed it, so a restarted
node waits out what is left of it."""

import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.steps.backoff_registry import BackoffPolicy, BackoffRegistry
from p2pwatch.application.steps.backoff_saver import BackoffSaver
from p2pwatch.domain.client_errors import SearchFailedError
from p2pwatch.domain.identifiers import Channel, ClientName
from p2pwatch.domain.search.backoff import BackoffKey, BackoffState
from tests.fakes.adapters.driven.fake_backoff_state_store import FakeBackoffStateStore
from tests.fakes.adapters.driven.fake_jitter_generator import FakeJitterGenerator
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_time import FakeTime

_KAD = BackoffKey(client_name=ClientName("amuled"), channel=Channel("kad"))
_ED2K = BackoffKey(client_name=ClientName("amuled"), channel=Channel("ed2k"))
_POLICY = BackoffPolicy(base_seconds=60.0, cap_seconds=600.0, factor=2.0, jitter_ratio=0.0)


class _Searches:
    """A backoff saver over a registry and its store, the searches played by hand on one fake
    timeline."""

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

    def kad_refused(self) -> None:
        with self.saver.saving():
            self.backoff.record_failure(_KAD)

    def kad_refused_then_left_by(self, error: BaseException) -> None:
        with self.saver.saving():
            self.backoff.record_failure(_KAD)
            raise error

    def kad_answered(self) -> None:
        with self.saver.saving():
            self.backoff.reset(_KAD)


def test_a_search_that_changed_the_backoff_saves_it_and_one_that_did_not_saves_nothing() -> None:
    searches = _Searches()

    searches.kad_refused()
    searches.kad_refused()  # within the wait the first set: the same attempt, nothing changed
    searches.kad_answered()
    searches.kad_answered()

    assert [set(saved) for saved in searches.state.saved] == [{_KAD}, set()]


def test_the_backoff_resumed_at_the_start_is_not_saved_again() -> None:
    searches = _Searches()
    resumed = {
        _ED2K: BackoffState(
            attempts=1, started_at=searches.fake_time.wall.now(), delay=timedelta(seconds=60)
        )
    }
    searches.state.set_backoff_states(resumed)  # the previous run's save
    searches.backoff.resume_waits()  # as the lifecycle does, once every search is built

    searches.kad_answered()

    assert searches.state.saved == [resumed]


def test_a_refused_save_is_logged_and_tried_again_after_the_next_search() -> None:
    searches = _Searches()
    searches.state.failures = 1

    searches.kad_refused()
    searches.fake_time.advance(timedelta(seconds=60))
    searches.kad_refused()

    assert searches.logger.lines == [
        LoggedLine(
            level="error",
            message="backoff not saved (database is locked): retried after the next search",
        )
    ]
    second_attempt = BackoffState(
        attempts=2,
        started_at=searches.fake_time.wall.now(),
        delay=timedelta(seconds=120),
    )
    assert searches.state.saved == [{_KAD: second_attempt}]


@pytest.mark.parametrize(
    "error",
    [SearchFailedError("refused"), asyncio.CancelledError()],
    ids=["a-search-that-raised", "a-search-cancelled"],
)
def test_a_search_left_by_an_exception_after_changing_the_backoff_still_saves_it(
    error: BaseException,
) -> None:
    searches = _Searches()

    with pytest.raises(type(error)):
        searches.kad_refused_then_left_by(error)

    assert [set(saved) for saved in searches.state.saved] == [{_KAD}]
