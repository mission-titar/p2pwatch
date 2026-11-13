import asyncio
from datetime import timedelta

import pytest

from p2pwatch.domain.client_errors import (
    ClientUnreachableError,
    DownloadRejectedError,
    ReadRejectedError,
)
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock
from tests.fakes.adapters.driven.fake_broken_free_space_meter import FakeBrokenFreeSpaceMeter
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.download_cycle import (
    HASH_A,
    HASH_B,
    build_cycle,
    candidate,
    observation,
    started,
    status,
)
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

# A refused read is the daemon unavailable, not a download refused.
_UNAVAILABLE = [ClientUnreachableError("daemon down"), ReadRejectedError("amuled_rejected")]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", _UNAVAILABLE, ids=["unreachable", "rejected"])
async def test_unreachable_client_is_tolerated_and_iteration_skipped(failure: Exception) -> None:
    client = FakeDownloadClient(list_failures=[failure])
    tracked_download_store = FakeTrackedDownloadStore()
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=FakeDecisionReader(
            candidates=(candidate(HASH_A, target_id=TargetId("062A")),)
        ),
    )
    await cycle.run_once()  # does not raise
    assert client.started == []  # iteration skipped (no candidates processed)


@pytest.mark.asyncio
async def test_store_error_is_absorbed() -> None:
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore(
        fail_record=True
    )  # record_queued raises StoreError
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, target_id=TargetId("062A")),)
    )
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, filename="x", size_bytes=1)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()  # does not raise (StoreError absorbed)


@pytest.mark.asyncio
async def test_start_unreachable_keeps_queued_and_is_tolerated() -> None:
    # start raises ClientUnreachableError → tolerated at cycle level; the download stays QUEUED
    # (record_queued already happened) → caught up next round. write-before-network invariant.
    client = FakeDownloadClient(start_failures=[ClientUnreachableError("down")])
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, target_id=TargetId("062A")),)
    )
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, filename="x", size_bytes=1)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()  # does not raise
    assert tracked_download_store.states[HASH_A] is DownloadState.QUEUED  # stays queued → caught up
    assert client.started == []


@pytest.mark.asyncio
async def test_completion_and_new_candidate_in_the_same_cycle() -> None:
    # HASH_A completed via the SHARED files (recorded this cycle); HASH_B is a new candidate
    # (queued + link).
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_B, target_id=TargetId("062A")),)
    )
    observation_reader = FakeObservationReader(
        observations={HASH_B: observation(HASH_B, filename="b.avi", size_bytes=100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()
    assert (
        tracked_download_store.states[HASH_A] is DownloadState.COMPLETED
    )  # shared and out of the queue
    assert tracked_download_store.states[HASH_B] is DownloadState.QUEUED  # new → enqueued
    assert HASH_B in started(client)  # + link emitted


@pytest.mark.asyncio
async def test_completion_store_failure_does_not_starve_new_candidates() -> None:
    # handle_completions raises StoreError (set_completed fails on the shared hash HASH_A)
    # → queue_new_candidates AND start_unlisted run ANYWAY for HASH_B:
    # a step-2 store failure does not starve step 3 (anti-starvation, I2).
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    tracked_download_store = FakeTrackedDownloadStore(
        fail_set_completed_for={HASH_A}
    )  # step 2 raises StoreError
    tracked_download_store.states[HASH_A] = (
        DownloadState.DOWNLOADING
    )  # completed at step 2, which raises
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_B, target_id=TargetId("062A")),)  # new candidate step 3
    )
    observation_reader = FakeObservationReader(
        observations={HASH_B: observation(HASH_B, filename="b.avi", size_bytes=100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()  # does not raise
    # Observable effect of step 3: HASH_B enqueued AND its link emitted despite the step-2 failure.
    assert tracked_download_store.states[HASH_B] is DownloadState.QUEUED
    assert HASH_B in started(client)
    # HASH_A stays DOWNLOADING: set_completed failed in step 2, retried next round.
    assert tracked_download_store.states[HASH_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_candidate_store_failure_does_not_starve_completions() -> None:
    # Symmetric: queue_new_candidates raises StoreError (record_queued fails) → the
    # step-2 completions were recorded ANYWAY (observable effect). The failure of
    # step 3 does not starve step 2.
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    tracked_download_store = FakeTrackedDownloadStore(fail_record=True)  # step 3 raises StoreError
    # HASH_A shared → completed step 2
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(
        candidates=(
            candidate(HASH_B, target_id=TargetId("062A")),
        )  # new candidate → record_queued will raise
    )
    observation_reader = FakeObservationReader(
        observations={HASH_B: observation(HASH_B, filename="b.avi", size_bytes=100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()  # does not raise
    # Observable effect of step 2: HASH_A completed despite the step-3 failure.
    assert tracked_download_store.states[HASH_A] is DownloadState.COMPLETED
    # HASH_B was NOT enqueued (record_queued raised) → no link emitted for it.
    assert HASH_B not in tracked_download_store.states
    assert client.started == []


@pytest.mark.asyncio
async def test_monitor_unreachable_aborts_subsequent_steps() -> None:
    # ClientUnreachableError at step 0 (downloads) = dead daemon → ABORT of the iteration:
    # neither the completions (step 2) nor the new candidates (step 3) must run.
    # (Doctrine "a dead daemon fails everything", distinct from StoreError isolation.)
    client = FakeDownloadClient(list_failures=[ClientUnreachableError("daemon down")])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.COMPLETED  # a pending completion (step 2)
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_B, target_id=TargetId("062A")),)  # a candidate (step 3)
    )
    observation_reader = FakeObservationReader(
        observations={HASH_B: observation(HASH_B, filename="b.avi", size_bytes=100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()  # does not raise (tolerated) but EVERYTHING is skipped
    assert tracked_download_store.states[HASH_A] is DownloadState.COMPLETED  # unchanged
    assert HASH_B not in tracked_download_store.states  # step 3 NOT executed
    assert client.started == []


@pytest.mark.asyncio
async def test_monitor_store_failure_is_isolated_and_does_not_starve_candidates() -> None:
    # reconcile_states raises StoreError (set_state fails during reconciliation) → step 1 is
    # ISOLATED (log + continue), it does NOT starve step 3: HASH_B is enqueued anyway.
    client = FakeDownloadClient(listed=[(status(HASH_A, done=10, total=10),)])
    tracked_download_store = FakeTrackedDownloadStore(fail_set_state_for={HASH_A})
    tracked_download_store.states[HASH_A] = (
        DownloadState.QUEUED
    )  # reconciled → set_state(DOWNLOADING) will raise
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_B, target_id=TargetId("062A")),)
    )
    observation_reader = FakeObservationReader(
        observations={HASH_B: observation(HASH_B, filename="b.avi", size_bytes=100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()  # does not raise
    # Step 3 ran despite the step-1 failure: HASH_B enqueued + link emitted.
    assert tracked_download_store.states[HASH_B] is DownloadState.QUEUED
    assert HASH_B in started(client)


@pytest.mark.asyncio
async def test_start_store_failure_is_tolerated_and_does_not_raise() -> None:
    # start_unlisted raises StoreError (set_state fails while marking a rejected start) →
    # tolerated (log), the cycle does not raise. Contract "never raises".
    # start rejected → start_unlisted tries set_state(FAILED), which raises
    # StoreError.
    client = FakeDownloadClient(start_failures=[DownloadRejectedError("rejected")])
    tracked_download_store = FakeTrackedDownloadStore(fail_set_state_for={HASH_A})
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, target_id=TargetId("062A")),)
    )
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, filename="x", size_bytes=1)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run_once()  # does NOT raise (step-4 StoreError tolerated)


@pytest.mark.asyncio
async def test_an_unmeasurable_output_directory_admits_nothing_and_does_not_raise() -> None:
    # A missing output mount must not take the crawler down: it also catalogues, which is the
    # primary mission. Refusing every candidate is the conservative degradation.
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, target_id=TargetId("062A")),)
    )
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, filename="x", size_bytes=100)}
    )
    observability = ObservabilityOverFakes()
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free_space_meter=FakeBrokenFreeSpaceMeter(),
        observability_dispatcher=observability.dispatcher,
    )
    await cycle.run_once()
    assert client.started == []
    assert HASH_A not in tracked_download_store.states
    assert observability.logger.lines == []
    assert observability.node_metric_store.read_samples() == ()


@pytest.mark.asyncio
async def test_the_first_turn_waits_for_nothing() -> None:
    waker = FakeWaker()
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        waker=waker,
        wait_clock=FakeBlockingMonotonicClock(),
    )
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert waker.waited_subjects == []


@pytest.mark.asyncio
async def test_a_later_turn_waits_the_poll_interval() -> None:
    fake_time = FakeTime()
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        fake_time=fake_time,
        poll_interval_seconds=30.0,
    )
    await cycle.run_once()
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert fake_time.sleeps == [timedelta(seconds=30)]


@pytest.mark.asyncio
async def test_a_turn_that_raised_still_makes_the_next_wait_the_poll_interval() -> None:
    fake_time = FakeTime()
    cycle = build_cycle(
        client=FakeDownloadClient(list_failures=[RuntimeError("bug")]),
        tracked_download_store=FakeTrackedDownloadStore(),
        fake_time=fake_time,
    )
    with pytest.raises(RuntimeError):
        await cycle.run_once()
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert fake_time.sleeps == [timedelta(seconds=30)]


@pytest.mark.asyncio
async def test_the_download_wake_ends_the_wait_and_cancels_the_pending_sleep() -> None:
    waker = FakeWaker()
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        waker=waker,
        wait_clock=FakeBlockingMonotonicClock(),  # the sleep never ends: the wake must win
    )
    await cycle.run_once()
    waker.wake(WakeSubject.DOWNLOAD)
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert waker.waited_subjects == [WakeSubject.DOWNLOAD]


@pytest.mark.asyncio
async def test_a_wait_cancelled_at_shutdown_propagates_the_cancellation() -> None:
    waker = FakeWaker()
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        waker=waker,
        wait_clock=FakeBlockingMonotonicClock(),
    )
    await cycle.run_once()
    task = asyncio.ensure_future(cycle.wait_for_next_turn())
    while WakeSubject.DOWNLOAD not in waker.waited_subjects:
        await asyncio.sleep(0)  # noqa: TID251
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


def test_the_supervisor_names_the_work_download_tracking() -> None:
    cycle = build_cycle(
        client=FakeDownloadClient(), tracked_download_store=FakeTrackedDownloadStore()
    )
    assert str(cycle) == "download tracking"
