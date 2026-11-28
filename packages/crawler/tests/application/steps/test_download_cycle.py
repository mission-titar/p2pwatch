import asyncio
from datetime import timedelta

import pytest

from p2pwatch.application.ports.driven.free_space_meter import FreeSpaceMeter
from p2pwatch.application.ports.driven.monotonic_clock import MonotonicClock
from p2pwatch.application.steps.download_cycle import DownloadCycle
from p2pwatch.application.steps.function_progress import FunctionProgress
from p2pwatch.application.steps.stall_watch import StallWatch
from p2pwatch.domain.client_errors import (
    ClientAuthError,
    ClientUnreachableError,
    DownloadRejectedError,
    ReadRejectedError,
)
from p2pwatch.domain.download.policy import DownloadVerdict
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.identifiers import ClientName
from p2pwatch.domain.matching.identifiers import TargetId
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.wake_subject import WakeSubject
from tests.fakes.adapters.driven.fake_blocking_monotonic_clock import FakeBlockingMonotonicClock
from tests.fakes.adapters.driven.fake_broken_free_space_meter import FakeBrokenFreeSpaceMeter
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import FakeLogger
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.fakes.adapters.driven.fake_waker import FakeWaker
from tests.support.application.steps.download_cycle import (
    DOWNLOADS,
    HASH_A,
    HASH_B,
    NODE_ID,
    DownloadsProgress,
    build_cycle,
    candidate,
    observation,
    started,
    status,
)
from tests.support.application.steps.node_health import build_node_health
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes

# A refused read is the daemon unavailable, not a download refused.
_UNAVAILABLE = [ClientUnreachableError("daemon down"), ReadRejectedError("amuled_rejected")]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", _UNAVAILABLE, ids=["unreachable", "rejected"])
async def test_an_unavailable_client_skips_the_round_moving_the_downloads_not(
    failure: Exception,
) -> None:
    client = FakeDownloadClient(list_failures=[failure])
    tracked_download_store = FakeTrackedDownloadStore()
    downloads = DownloadsProgress()
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=FakeDecisionReader(
            candidates=(candidate(HASH_A, target_id=TargetId("062A")),)
        ),
        function_progress=downloads.function_progress,
    )
    assert not await downloads.moved_by(cycle)  # does not raise
    assert client.started == []  # iteration skipped (no candidates processed)


@pytest.mark.asyncio
async def test_a_candidate_store_error_is_absorbed_moving_the_downloads_not() -> None:
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
    downloads = DownloadsProgress()
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        function_progress=downloads.function_progress,
    )
    assert not await downloads.moved_by(cycle)  # does not raise (StoreError absorbed)


@pytest.mark.asyncio
async def test_start_unreachable_keeps_queued_and_is_tolerated_moving_the_downloads_not() -> None:
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
    downloads = DownloadsProgress()
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        function_progress=downloads.function_progress,
    )
    assert not await downloads.moved_by(cycle)  # does not raise
    assert tracked_download_store.states[HASH_A] is DownloadState.QUEUED  # stays queued → caught up
    assert client.started == []


@pytest.mark.asyncio
async def test_completion_and_new_candidate_in_the_same_cycle_moving_the_downloads() -> None:
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
    downloads = DownloadsProgress()
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        function_progress=downloads.function_progress,
    )
    assert await downloads.moved_by(cycle)
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
async def test_start_store_failure_is_tolerated_moving_the_downloads_not() -> None:
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
    downloads = DownloadsProgress()
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        function_progress=downloads.function_progress,
    )
    assert not await downloads.moved_by(cycle)  # does NOT raise (step-4 StoreError tolerated)


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


async def _alerts_over_a_quarter_hour(
    *, target_id: TargetId, size_bytes: int, free_space_meter: FreeSpaceMeter, logger: FakeLogger
) -> list[tuple[int, str]]:
    """Each alert's minute and first line while amuled's downloads take a round a minute on one
    candidate for 15 min, the stall watch looking before each round."""
    fake_time, observability = FakeTime(), ObservabilityOverFakes()
    progress = FunctionProgress(monotonic_clock=fake_time.monotonic)
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        decision_reader=FakeDecisionReader(candidates=(candidate(HASH_A, target_id=target_id),)),
        observation_reader=FakeObservationReader(
            observations={HASH_A: observation(HASH_A, filename="x", size_bytes=size_bytes)}
        ),
        free_space_meter=free_space_meter,
        observability_dispatcher=observability.dispatcher,
        fake_time=fake_time,
        logger=logger,
        function_progress=progress,
    )
    watch = StallWatch(
        client_name=ClientName("amuled"),
        watched=[DOWNLOADS],
        function_progress=progress,
        node_health=build_node_health(observability_dispatcher=observability.dispatcher),
        monotonic_clock=fake_time.monotonic,
        node_id=NODE_ID,
    )
    alerts: list[tuple[int, str]] = []
    for minute in range(16):
        already = len(observability.notifications)
        await watch.run_once()
        await cycle.run_once()
        sent = observability.notifications[already:]
        alerts += [
            (minute, alert.message) for _, alert in sent if isinstance(alert, RelayedLogLine)
        ]
        fake_time.advance(timedelta(minutes=1))
    return alerts


# A target the config no longer lists counts as complete; 2 MB do not fit in the 1 MB free.
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_id", "size_bytes", "verdict"),
    [
        (TargetId("S9E999Z"), 1, DownloadVerdict.SKIP_COMPLETE),
        (TargetId("062A"), 2_000_000, DownloadVerdict.SKIP_DISK_CAP),
    ],
    ids=["complete", "deferred-for-disk-space"],
)
async def test_rounds_skipping_or_deferring_their_candidate_stall_nothing(
    *, target_id: TargetId, size_bytes: int, verdict: DownloadVerdict
) -> None:
    logger = FakeLogger()

    alerts = await _alerts_over_a_quarter_hour(
        target_id=target_id,
        size_bytes=size_bytes,
        free_space_meter=FakeFreeSpaceMeter(1_000_000),
        logger=logger,
    )

    assert alerts == []
    assert f"candidate file={HASH_A} → {verdict.value} (skipped/deferred)" in [
        line.message for line in logger.lines
    ]


@pytest.mark.asyncio
async def test_an_output_directory_removed_stalls_the_downloads_at_15_min() -> None:
    alerts = await _alerts_over_a_quarter_hour(
        target_id=TargetId("062A"),
        size_bytes=1,
        free_space_meter=FakeBrokenFreeSpaceMeter(),
        logger=FakeLogger(),
    )

    assert alerts == [(15, "downloads stalled on amuled for 15 min")]


def _idle_cycle(*, wait_clock: MonotonicClock, waker: FakeWaker | None = None) -> DownloadCycle:
    """A cycle with nothing to track, its wait sleeping on ``wait_clock``."""
    return build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        waker=waker,
        wait_clock=wait_clock,
    )


async def _until_waiting_for_a_download_wake(waker: FakeWaker) -> None:
    while WakeSubject.DOWNLOAD not in waker.waited_subjects:
        await asyncio.sleep(0)  # noqa: TID251


def _other_tasks() -> set[asyncio.Task[object]]:
    return asyncio.all_tasks() - {asyncio.current_task()}


@pytest.mark.asyncio
async def test_the_first_turn_starts_at_once() -> None:
    waker = FakeWaker()
    cycle = _idle_cycle(wait_clock=FakeBlockingMonotonicClock(), waker=waker)
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert waker.waited_subjects == []


@pytest.mark.asyncio
async def test_after_a_turn_the_next_waits_the_poll_interval() -> None:
    fake_time = FakeTime()
    cycle = _idle_cycle(wait_clock=fake_time.monotonic)
    await cycle.run_once()
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert fake_time.sleeps == [timedelta(seconds=30)]


@pytest.mark.asyncio
async def test_after_a_turn_that_raised_the_next_waits_the_poll_interval_too() -> None:
    fake_time = FakeTime()
    cycle = build_cycle(
        client=FakeDownloadClient(list_failures=[ClientAuthError("amuleapi refused the password")]),
        tracked_download_store=FakeTrackedDownloadStore(),
        wait_clock=fake_time.monotonic,
    )
    with pytest.raises(ClientAuthError):
        await cycle.run_once()
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert fake_time.sleeps == [timedelta(seconds=30)]


@pytest.mark.asyncio
async def test_a_wake_set_before_the_wait_ends_it_at_once_and_cancels_the_polls_sleep() -> None:
    waker = FakeWaker()
    cycle = _idle_cycle(wait_clock=FakeBlockingMonotonicClock(), waker=waker)
    await cycle.run_once()
    waker.wake(WakeSubject.DOWNLOAD)  # a download decision, as the cataloguer makes one
    await asyncio.wait_for(cycle.wait_for_next_turn(), timeout=1.0)
    assert _other_tasks() == set()


@pytest.mark.asyncio
async def test_a_wake_during_the_wait_ends_it_and_cancels_the_polls_sleep() -> None:
    waker = FakeWaker()
    cycle = _idle_cycle(wait_clock=FakeBlockingMonotonicClock(), waker=waker)
    await cycle.run_once()
    wait = asyncio.ensure_future(cycle.wait_for_next_turn())
    await asyncio.wait_for(_until_waiting_for_a_download_wake(waker), timeout=1.0)
    waker.wake(WakeSubject.DOWNLOAD)  # a download decision, as the cataloguer makes one
    await asyncio.wait_for(wait, timeout=1.0)
    assert _other_tasks() == set()


@pytest.mark.asyncio
async def test_a_wait_cancelled_at_the_shutdown_raises_and_leaves_no_task() -> None:
    waker = FakeWaker()
    cycle = _idle_cycle(wait_clock=FakeBlockingMonotonicClock(), waker=waker)
    await cycle.run_once()
    wait = asyncio.ensure_future(cycle.wait_for_next_turn())
    await asyncio.wait_for(_until_waiting_for_a_download_wake(waker), timeout=1.0)
    wait.cancel()
    with pytest.raises(asyncio.CancelledError):
        await wait
    assert _other_tasks() == set()


def test_download_tracking_is_named_after_its_client() -> None:
    cycle = build_cycle(
        client=FakeDownloadClient(), tracked_download_store=FakeTrackedDownloadStore()
    )
    assert str(cycle) == "download tracking amuled"
