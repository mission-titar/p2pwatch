from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from p2pwatch.adapters.driven.persistence_sqlite.connection import open_local
from p2pwatch.adapters.driven.persistence_sqlite.sqlite_tracked_download_store import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.application.steps.download_cycle import run_download_cycle
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.observability.notification import CompletedDownload
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_no_set_state_tracked_download_store import (
    FakeNoSetStateTrackedDownloadStore,
)
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_ticking_wall_clock import FakeTickingWallClock
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_deps import (
    HASH_A,
    HASH_B,
    NODE,
    build_deps,
    candidate,
    key,
    observation,
    status,
)
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes


@pytest.mark.asyncio
async def test_monitor_marks_in_progress_when_not_complete() -> None:
    client = FakeDownloadClient(listed=[(status(HASH_A, done=3, total=10),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.QUEUED
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_monitor_does_not_regress_a_completed_queue_entry() -> None:
    # reconcile_states: a COMPLETED hash present in the amuled queue MUST NOT regress to
    # DOWNLOADING (the completion notification already fired; re-firing it would be noise).
    client = FakeDownloadClient(listed=[(status(HASH_A, done=3, total=10),)])
    tracked_download_store = FakeNoSetStateTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.COMPLETED
    deps = build_deps(client=client, tracked_download_store=tracked_download_store)
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.COMPLETED  # unchanged


@pytest.mark.asyncio
async def test_monitor_resurrects_a_failed_download_back_in_the_queue() -> None:
    # amuled is the authority on what it holds: a hash the TTL condemned (or a start
    # amuled rejected) that shows up in the queue is downloading again.
    client = FakeDownloadClient(listed=[(status(HASH_A, done=3, total=10),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.FAILED
    tracked_download_store.failures[HASH_A] = FailureReason.LOST
    deps = build_deps(client=client, tracked_download_store=tracked_download_store)
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.DOWNLOADING
    assert tracked_download_store.failures[HASH_A] is None


@pytest.mark.asyncio
async def test_monitor_ignores_unknown_queue_entries() -> None:
    # an entry in the amuled queue but unknown to downloads (started outside crawler) is ignored.
    client = FakeDownloadClient(listed=[(status(HASH_B, done=10, total=10),)])
    tracked_download_store = FakeTrackedDownloadStore()
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    assert HASH_B not in tracked_download_store.states


@pytest.mark.asyncio
async def test_every_byte_received_is_not_a_completion() -> None:
    # Field 2026-09-02: 065B was marked COMPLETED while amuled still held it as a partfile. Only
    # the client's own signal completes a download, never a byte count (stage 2, D10).
    client = FakeDownloadClient(listed=[(status(HASH_A, done=100, total=100),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    deps = build_deps(client=client, tracked_download_store=tracked_download_store)
    await run_download_cycle(deps, NODE)
    assert (
        tracked_download_store.states[HASH_A] is DownloadState.DOWNLOADING
    )  # NOT flipped to COMPLETED


@pytest.mark.asyncio
async def test_one_hash_store_failure_does_not_starve_other_completions() -> None:
    # Regression error-boundary#2: a ``StoreError`` in ``_record_completion`` of hash N
    # used to bubble up to the cycle handler, abandoning N+1, N+2 of the same snapshot. The fix
    # isolates PER HASH (try/except around _record_completion), honoring the "isolated per
    # step" intent of the comment (I2).
    client = FakeDownloadClient(
        listed=[
            (
                status(HASH_A, completed=True),
                status(HASH_B, completed=True),
            )
        ],
    )
    # HASH_A and HASH_B in DOWNLOADING; set_completed(HASH_A, ...) crashes → its completion
    # raises; HASH_B must nonetheless be completed (intra-cycle continuity).
    tracked_download_store = FakeTrackedDownloadStore(fail_set_completed_for={HASH_A})
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.DOWNLOADING
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    # despite the failure on HASH_A
    assert tracked_download_store.states[HASH_B] is DownloadState.COMPLETED


@pytest.mark.asyncio
async def test_monitor_no_op_when_state_already_matches() -> None:
    # reconcile_states: in-progress entry (done=3/full=10) and store already DOWNLOADING →
    # wanted_state is current → NO set_state (FALSE branch of `if current is not wanted_state`).
    client = FakeDownloadClient(listed=[(status(HASH_A, done=3, total=10),)])
    tracked_download_store = FakeNoSetStateTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_shared_file_for_tracked_hash_is_completed() -> None:
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.COMPLETED


@pytest.mark.asyncio
async def test_shared_file_for_untracked_hash_is_ignored() -> None:
    tracked_download_store = FakeTrackedDownloadStore()  # HASH_A not tracked by the crawler
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    assert HASH_A not in tracked_download_store.states


@pytest.mark.asyncio
async def test_already_completed_shared_hash_is_not_recompleted() -> None:
    # A completed file stays in amuled's shared list forever. Without the terminal skip, every
    # cycle would re-stamp it and re-fire the community notification.
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.COMPLETED
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        observability_dispatcher=observability.dispatcher,
    )
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.completed_at == {}
    assert observability.notifier.calls == []


@pytest.mark.asyncio
async def test_failed_shared_hash_is_resurrected_and_notified() -> None:
    # The TTL can condemn a download that had in fact completed and been moved out of
    # IncomingDir. Finding it shared afterwards is amuled saying it exists: complete + notify.
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.FAILED
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        observability_dispatcher=observability.dispatcher,
    )
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.COMPLETED
    [(_, notification)] = observability.notifier.calls
    assert isinstance(notification, CompletedDownload)


@pytest.mark.asyncio
async def test_monitor_moves_queued_to_downloading_not_completed() -> None:
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.QUEUED
    client = FakeDownloadClient(listed=[(status(HASH_A, done=10, total=10),)])
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    assert (
        tracked_download_store.states[HASH_A] is DownloadState.DOWNLOADING
    )  # NOT completed (bytes ignored)


@pytest.mark.asyncio
async def test_marks_seen_every_listed_download_completed_ones_included() -> None:
    # Stamping must happen BEFORE the TTL is evaluated.
    client = FakeDownloadClient(
        listed=[(status(HASH_A, done=3, total=10), status(HASH_B, completed=True))]
    )
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.COMPLETED
    deps = build_deps(client=client, tracked_download_store=tracked_download_store)
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.seen == [{HASH_A, HASH_B}]


@pytest.mark.asyncio
async def test_a_download_amuled_no_longer_knows_becomes_failed() -> None:
    client, fake_time = FakeDownloadClient(listed=[(status(HASH_A),), ()]), FakeTime()
    logger = FakeLogger()
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.record_queued(key(HASH_A), "062A", 1, fake_time.wall.now())
    observation_reader = FakeObservationReader(observations={HASH_A: observation(HASH_A, "a", 1)})
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        observation_reader=observation_reader,
        lost_after=timedelta(hours=1),
        fake_time=fake_time,
        logger=logger,
    )
    await run_download_cycle(deps, NODE)
    fake_time.advance(timedelta(hours=1))
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.FAILED
    assert tracked_download_store.failures[HASH_A] is FailureReason.LOST
    assert client.started == []  # failed by the TTL: never started again
    assert (
        LoggedLine("warning", f"file={HASH_A} unseen by the client for 3600.0s: marked failed")
        in logger.lines
    )


@pytest.mark.asyncio
async def test_each_download_write_carries_the_instant_read_right_before_it() -> None:
    wall_clock = FakeTickingWallClock(FakeTime())
    start = wall_clock.now()
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_B, "062A"),))
    observation_reader = FakeObservationReader(
        observations={HASH_B: observation(HASH_B, "b.avi", 100)}
    )
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        wall_clock=wall_clock,
    )
    await run_download_cycle(deps, NODE)
    minute = timedelta(minutes=1)
    assert tracked_download_store.completed_at == {HASH_A: start + minute}
    assert tracked_download_store.seen_at == [start + 2 * minute]
    assert tracked_download_store.queued_at == {HASH_B: start + 3 * minute}


@pytest.mark.asyncio
async def test_a_failure_the_client_reports_stays_failed_round_after_round() -> None:
    # Stage 2, D12: an erroneous partfile is failed, and a listing without progress does not
    # flap it back to downloading each round.
    erroneous = status(HASH_A, done=3, total=10, failure=FailureReason.ERROR)
    client = FakeDownloadClient(listed=[(erroneous,)] * 3)
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    deps = build_deps(client=client, tracked_download_store=tracked_download_store)
    rounds = []
    for _ in range(3):
        await run_download_cycle(deps, NODE)
        rounds.append(
            (tracked_download_store.states[HASH_A], tracked_download_store.failures.get(HASH_A))
        )
    assert rounds == [(DownloadState.FAILED, FailureReason.ERROR)] * 3
    assert client.started == []


@pytest.mark.asyncio
async def test_waiting_for_sources_is_not_failing_for_a_simulated_year(tmp_path: Path) -> None:
    # The real TTL of one day, a month between rounds, the client listing the download each one.
    fake_time = FakeTime()
    connection = open_local(tmp_path / "local.db")
    tracked_download_store = SqliteTrackedDownloadStore(connection)
    tracked_download_store.record_queued(key(HASH_A), "062A", 10, fake_time.wall.now())
    waiting = status(HASH_A, total=10, waiting=WaitingReason.NO_SOURCE)
    client = FakeDownloadClient(listed=[(waiting,)] * 12)
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    for _ in range(12):
        fake_time.advance(timedelta(days=30))
        await run_download_cycle(deps, NODE)
    row = connection.execute("SELECT state, waiting_reason, failure_reason FROM downloads")
    assert row.fetchall() == [("downloading", "no_source", None)]
    connection.close()


@pytest.fixture
def real_tracked_download_store(tmp_path: Path) -> Iterator[SqliteTrackedDownloadStore]:
    connection = open_local(tmp_path / "local.db")
    yield SqliteTrackedDownloadStore(connection)
    connection.close()


@pytest.mark.asyncio
async def test_a_wall_clock_step_forward_fails_no_download_absent_from_one_poll(
    real_tracked_download_store: SqliteTrackedDownloadStore,
) -> None:
    fake_time = FakeTime()
    real_tracked_download_store.record_queued(key(HASH_A), "062A", 10, fake_time.wall.now())
    deps = build_deps(
        client=FakeDownloadClient(listed=[(status(HASH_A, total=10),), ()]),
        tracked_download_store=real_tracked_download_store,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    fake_time.step_wall(timedelta(days=2))
    await run_download_cycle(deps, NODE)
    assert real_tracked_download_store.read_tracked_states() == {
        key(HASH_A): DownloadState.DOWNLOADING
    }


@pytest.mark.asyncio
async def test_a_latest_seen_at_in_the_future_waits_lost_after_no_more(
    real_tracked_download_store: SqliteTrackedDownloadStore,
) -> None:
    # Stamped before the wall clock stepped back an hour, while the node was down.
    fake_time = FakeTime()
    real_tracked_download_store.record_queued(
        key(HASH_A), "062A", 10, fake_time.wall.now() + timedelta(hours=1)
    )
    deps = build_deps(
        client=FakeDownloadClient(),
        tracked_download_store=real_tracked_download_store,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    fake_time.advance(timedelta(days=1) - timedelta(seconds=1))
    await run_download_cycle(deps, NODE)
    assert real_tracked_download_store.read_tracked_states() == {key(HASH_A): DownloadState.QUEUED}
    fake_time.advance(timedelta(seconds=1))
    await run_download_cycle(deps, NODE)
    assert real_tracked_download_store.read_tracked_states() == {key(HASH_A): DownloadState.FAILED}


@pytest.mark.asyncio
async def test_a_download_last_seen_two_days_ago_fails_at_the_first_cycle(
    real_tracked_download_store: SqliteTrackedDownloadStore,
) -> None:
    fake_time = FakeTime()
    real_tracked_download_store.record_queued(
        key(HASH_A), "062A", 10, fake_time.wall.now() - timedelta(days=2)
    )
    deps = build_deps(
        client=FakeDownloadClient(),
        tracked_download_store=real_tracked_download_store,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    assert real_tracked_download_store.read_tracked_states() == {key(HASH_A): DownloadState.FAILED}


@pytest.mark.asyncio
async def test_a_download_the_node_queued_is_lost_after_lost_after_of_monotonic_time(
    real_tracked_download_store: SqliteTrackedDownloadStore,
) -> None:
    fake_time = FakeTime()
    deps = build_deps(
        client=FakeDownloadClient(),  # never lists it
        tracked_download_store=real_tracked_download_store,
        decision_reader=FakeDecisionReader(candidates=(candidate(HASH_A, "062A"),)),
        observation_reader=FakeObservationReader(
            observations={HASH_A: observation(HASH_A, "a.avi", 10)}
        ),
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)
    fake_time.step_wall(timedelta(days=2))
    await run_download_cycle(deps, NODE)
    assert real_tracked_download_store.read_tracked_states() == {key(HASH_A): DownloadState.QUEUED}
    fake_time.advance(timedelta(days=1))
    await run_download_cycle(deps, NODE)
    assert real_tracked_download_store.read_tracked_states() == {key(HASH_A): DownloadState.FAILED}


@pytest.mark.asyncio
async def test_a_row_the_operator_deleted_then_queued_again_waits_lost_after_anew() -> None:
    fake_time = FakeTime()
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.record_queued(key(HASH_A), "062A", 10, fake_time.wall.now())
    deps = build_deps(
        client=FakeDownloadClient(listed=[(status(HASH_A),)]),
        tracked_download_store=tracked_download_store,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, NODE)  # listed: lost a day from now
    del tracked_download_store.states[HASH_A]  # for a manual retry
    await run_download_cycle(deps, NODE)
    fake_time.advance(timedelta(hours=12))
    tracked_download_store.record_queued(key(HASH_A), "062A", 10, fake_time.wall.now())
    fake_time.advance(timedelta(hours=12))
    await run_download_cycle(deps, NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.QUEUED


@pytest.mark.asyncio
async def test_monitor_store_error_still_promotes_completions_in_same_cycle() -> None:
    # Regression logic-download#2: if ``reconcile_states`` raises ``StoreError`` (set_state
    # down on another hash), the old code set ``states={}`` then called ``handle_completions``
    # → each shared hash → ``states.get(...) is None`` → ignored → NO completion recorded
    # in the whole cycle (latency +1 cycle although we already have the signal). The fix re-reads
    # ``read_tracked_states()`` BEFORE ``handle_completions`` so the completions are seen.
    client = FakeDownloadClient(
        # HASH_A completed: the completion must be recorded in this very cycle. HASH_B is listed and
        # fails its set_state transition.
        listed=[(status(HASH_B), status(HASH_A, completed=True))],
    )
    tracked_download_store = FakeTrackedDownloadStore(fail_set_state_for={HASH_B})
    # HASH_A already DOWNLOADING (no transition by reconcile_states); HASH_B QUEUED → it will try
    # set_state(HASH_B, DOWNLOADING) which raises → step 1 crashes, but HASH_A is completed.
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    tracked_download_store.states[HASH_B] = DownloadState.QUEUED
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)
    # HASH_A's completion is recorded despite the failure of reconcile_states on HASH_B
    assert tracked_download_store.states[HASH_A] is DownloadState.COMPLETED


@pytest.mark.asyncio
async def test_tracked_states_store_failure_is_absorbed_at_step_2() -> None:
    # ``read_tracked_states`` that raises IN A LOOP (persistent store failure): step 1 absorbs, then
    # the re-read of step 2 (logic-download#2) absorbs in turn → the cycle ends without
    # crashing the loop (the next cycle will replay). We exercise HERE the branch
    # ``except StoreError`` of step 2 separately from that of step 1.
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore(fail_tracked_states=True)
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
    )
    await run_download_cycle(deps, NODE)  # does not raise (both StoreError are absorbed)


@pytest.mark.asyncio
async def test_presence_store_failure_is_absorbed_and_candidates_still_run() -> None:
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore(fail_set_seen=True)
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, "062A"),))
    observation_reader = FakeObservationReader(observations={HASH_A: observation(HASH_A, "x", 100)})
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, NODE)  # does not raise
    assert tracked_download_store.states[HASH_A] is DownloadState.QUEUED
