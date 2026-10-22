import sqlite3
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from catalog_matching.domain.models import TargetSegment
from p2pwatch.adapters.driven.persistence_sqlite.connection import open_catalog, open_local
from p2pwatch.adapters.driven.persistence_sqlite.download_repository import (
    SqliteTrackedDownloadStore,
)
from p2pwatch.adapters.driven.persistence_sqlite.source_repository import SqliteSourcePointStore
from p2pwatch.application.steps.run_download_cycle import DownloadDeps, run_download_cycle
from p2pwatch.domain.client_errors import ClientUnreachableError, DownloadRejectedError
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.states import DownloadState, FailureReason, WaitingReason
from p2pwatch.domain.download.status import DownloadStatus
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observability.events import (
    DiskSpaceLow,
    DownloadCompleted,
    DownloadQueued,
    FreeSpaceSampled,
    SourceFirstUseful,
    SourceReappeared,
    TargetTitle,
)
from p2pwatch.domain.observation import FileObservation, ReportedFile
from p2pwatch.domain.source import (
    EarlierPoints,
    RecordedReading,
    SourceKey,
    SourceReading,
    SourceRole,
)
from tests.fakes.adapters.driven.broken_disk import FakeBrokenFreeSpaceMeter
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_download_store import FakeTrackedDownloadStore
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import FakeLogger, LoggedLine
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_source_client import FakeSourceClient
from tests.fakes.adapters.driven.fake_source_point_store import FakeSourcePointStore
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.lagging_download_store import FakeLaggingTrackedDownloadStore
from tests.fakes.adapters.driven.no_set_state_store import FakeNoSetStateTrackedDownloadStore
from tests.fakes.adapters.driven.ticking_wall_clock import FakeTickingWallClock
from tests.support.catalog_rows import insert_file, source_variant_node_ids

_NODE = "n1"
_A = "a" * 32
_B = "b" * 32
_C = "c" * 32
_SEEN_AT = datetime(2026, 6, 12, tzinfo=UTC)

_TARGETS = (
    TargetSegment(
        season=2, seasonal_number=11, absolute_number=62, letter="A", title="t", status="lost"
    ),
    TargetSegment(
        season=2,
        seasonal_number=63,
        absolute_number=63,
        letter="A",
        title="t2",
        status="complete",
    ),
)


def _key(hash_hex: str) -> FileKey:
    return FileKey(Network.ED2K, hash_hex)


def _observation(hash_hex: str, filename: str, size_bytes: int) -> FileObservation:
    reported_file = ReportedFile(_key(hash_hex), filename, size_bytes, 1, "keroro")
    return FileObservation(reported_file, _SEEN_AT)


def _candidate(hash_hex: str, target_id: str) -> DownloadCandidate:
    return DownloadCandidate(file=_key(hash_hex), target_id=target_id)


def _status(
    hash_hex: str,
    *,
    done: int = 0,
    total: int = 0,
    completed: bool = False,
    waiting: WaitingReason | None = None,
    failure: FailureReason | None = None,
) -> DownloadStatus:
    return DownloadStatus(_key(hash_hex), done, total, completed, waiting, failure)


def _started(client: FakeDownloadClient) -> list[str]:
    return [request.file.native_id for request in client.started]


def _deps(
    *,
    client: FakeDownloadClient,
    source_client: FakeSourceClient | None = None,
    downloads: FakeTrackedDownloadStore | SqliteTrackedDownloadStore,
    decision_reader: FakeDecisionReader | None = None,
    observation_reader: FakeObservationReader | None = None,
    free: int = 1_000_000,
    min_free: int = 0,
    lost_after: timedelta = timedelta(days=1),
    event_emitter: FakeEventEmitter | None = None,
    targets: Sequence[TargetSegment] | None = None,
    sources: FakeSourcePointStore | SqliteSourcePointStore | None = None,
    fake_time: FakeTime | None = None,
    sources_interval: timedelta = timedelta(seconds=30),
    logger: FakeLogger | None = None,
) -> DownloadDeps:
    fake_time = fake_time or FakeTime()
    sources = sources or FakeSourcePointStore()
    return DownloadDeps(
        download_client=client,
        source_client=source_client or FakeSourceClient(),
        tracked_download_writer=downloads,
        tracked_download_reader=downloads,
        source_point_writer=sources,
        source_point_reader=sources,
        decision_reader=decision_reader or FakeDecisionReader(),
        observation_reader=observation_reader or FakeObservationReader(),
        targets=targets if targets is not None else _TARGETS,
        free_space_meter=FakeFreeSpaceMeter(free),
        min_free_bytes=min_free,
        lost_after=lost_after,
        poll_interval_seconds=30.0,
        reappeared_after=timedelta(hours=12),
        sources_interval=sources_interval,
        wall_clock=fake_time.wall,
        monotonic_clock=fake_time.monotonic,
        event_emitter=event_emitter or FakeEventEmitter(),
        logger=logger or FakeLogger(),
    )


@pytest.mark.asyncio
async def test_new_candidate_is_queued_and_link_added() -> None:
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(
        observations={_A: _observation(_A, "Keroro.avi", 100)}
    )
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.QUEUED
    assert client.started == [DownloadRequest(_key(_A), "Keroro.avi", 100)]


@pytest.mark.asyncio
async def test_already_downloaded_candidate_is_deduped() -> None:
    client = FakeDownloadClient(listed=[(_status(_A),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING  # already known
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert client.started == []  # dedup: no new link


@pytest.mark.asyncio
async def test_two_segment_candidates_same_hash_dedup_to_one_download() -> None:
    # spec §8: a whole-episode file yields BOTH (hash,062A) and (hash,062B) in
    # read_download_candidates; is_tracked(hash) dedups them to ONE physical download.
    #
    # Both targets are DOWNLOAD-eligible ("lost", not "complete") so the ONLY thing that
    # can collapse the two candidates is the `is_tracked(hash)` guard in
    # _queue_new_candidates, never `_target_status` falling back to its "complete"
    # default for an absent target (that would be an unrelated skip path, spec §6).
    targets = (
        TargetSegment(
            season=2, seasonal_number=11, absolute_number=62, letter="A", title="t", status="lost"
        ),
        TargetSegment(
            season=2, seasonal_number=12, absolute_number=62, letter="B", title="t", status="lost"
        ),
    )
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_A, "062A"), _candidate(_A, "062B"))
    )
    observation_reader = FakeObservationReader(
        observations={_A: _observation(_A, "Keroro 062.avi", 100)}
    )
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        event_emitter=event_emitter,
        targets=targets,
    )
    await run_download_cycle(deps, _NODE)
    assert list(downloads.states) == [_A]
    assert downloads.states[_A] is DownloadState.QUEUED
    assert _started(client) == [_A]
    # Load-bearing assertion: exactly ONE DownloadQueued event. _queue_new_candidates
    # emits one per NON-skipped candidate (run_download_cycle.py, end of the loop body);
    # both candidates are policy-eligible here, so a SECOND event would only appear if the
    # `is_tracked` continue-guard were removed, unlike the hash-keyed dict observables
    # above (states/started), which stay collapsed regardless thanks to
    # FakeTrackedDownloadStore.record_queued's own idempotency guard.
    queued_events = [e for e in event_emitter.events if isinstance(e, DownloadQueued)]
    assert len(queued_events) == 1


@pytest.mark.asyncio
async def test_complete_target_candidate_is_skipped() -> None:
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_B, "063A"),)  # 063A status=complete
    )
    observation_reader = FakeObservationReader(observations={_B: _observation(_B, "x", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert client.started == []
    assert _B not in downloads.states


@pytest.mark.asyncio
async def test_a_candidate_that_would_break_the_disk_floor_defers() -> None:
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 500)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1_000,
        min_free=600,  # 1000 - 500 < 600 → defers
    )
    await run_download_cycle(deps, _NODE)
    assert client.started == []
    assert _A not in downloads.states


@pytest.mark.asyncio
async def test_outstanding_queue_bytes_are_charged_against_the_floor() -> None:
    # Free space alone would admit this candidate; the 900 bytes amuled still has to fetch
    # for a download already running is what refuses it.
    client = FakeDownloadClient(listed=[(_status(_B, done=100, total=1000),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_B] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 200)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1_000,
        min_free=0,
    )
    await run_download_cycle(deps, _NODE)
    assert client.started == []
    assert _A not in downloads.states


@pytest.mark.asyncio
async def test_a_nascent_queue_entry_commits_nothing() -> None:
    # size_full == 0: amuled does not know the total yet. Charging size_full - size_done would
    # be NEGATIVE and invent free space, so the entry contributes zero and the candidate fits.
    client = FakeDownloadClient(listed=[(_status(_B, done=50, total=0),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_B] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 200)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1_000,
        min_free=800,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.QUEUED


@pytest.mark.asyncio
async def test_candidate_without_observation_is_skipped() -> None:
    # a candidate for which no observation survived (edge case) cannot build a link:
    # we skip it (log), never a crash.
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert client.started == []


@pytest.mark.asyncio
async def test_monitor_marks_in_progress_when_not_complete() -> None:
    client = FakeDownloadClient(listed=[(_status(_A, done=3, total=10),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.QUEUED
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_monitor_does_not_regress_a_completed_queue_entry() -> None:
    # _reconcile_states: a COMPLETED hash present in the amuled queue MUST NOT regress to
    # DOWNLOADING (the completion notification already fired; re-firing it would be noise).
    client = FakeDownloadClient(listed=[(_status(_A, done=3, total=10),)])
    tracked_download_store = FakeNoSetStateTrackedDownloadStore()
    tracked_download_store.states[_A] = DownloadState.COMPLETED
    deps = _deps(client=client, downloads=tracked_download_store)
    await run_download_cycle(deps, _NODE)
    assert tracked_download_store.states[_A] is DownloadState.COMPLETED  # unchanged


@pytest.mark.asyncio
async def test_monitor_resurrects_a_failed_download_back_in_the_queue() -> None:
    # amuled is the authority on what it holds: a hash the TTL condemned (or a start
    # amuled rejected) that shows up in the queue is downloading again.
    client = FakeDownloadClient(listed=[(_status(_A, done=3, total=10),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.FAILED
    downloads.failures[_A] = FailureReason.LOST
    deps = _deps(client=client, downloads=downloads)
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.DOWNLOADING
    assert downloads.failures[_A] is None


@pytest.mark.asyncio
async def test_monitor_ignores_unknown_queue_entries() -> None:
    # an entry in the amuled queue but unknown to downloads (started outside crawler) is ignored.
    client = FakeDownloadClient(listed=[(_status(_B, done=10, total=10),)])
    downloads = FakeTrackedDownloadStore()
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)
    assert _B not in downloads.states


@pytest.mark.asyncio
async def test_every_byte_received_is_not_a_completion() -> None:
    # Field 2026-09-02: 065B was marked COMPLETED while amuled still held it as a partfile. Only
    # the client's own signal completes a download, never a byte count (stage 2, D10).
    client = FakeDownloadClient(listed=[(_status(_A, done=100, total=100),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    deps = _deps(client=client, downloads=downloads)
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.DOWNLOADING  # NOT flipped to COMPLETED


# amuleapi refuses a read with ``amuled_rejected``, a DownloadRejectedError: on a read, the
# daemon is unavailable, not a download refused.
_UNAVAILABLE = [ClientUnreachableError("daemon down"), DownloadRejectedError("amuled_rejected")]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", _UNAVAILABLE, ids=["unreachable", "rejected"])
async def test_unreachable_client_is_tolerated_and_iteration_skipped(failure: Exception) -> None:
    client = FakeDownloadClient(list_failures=[failure])
    downloads = FakeTrackedDownloadStore()
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=FakeDecisionReader(candidates=(_candidate(_A, "062A"),)),
    )
    await run_download_cycle(deps, _NODE)  # does not raise
    assert client.started == []  # iteration skipped (no candidates processed)


@pytest.mark.asyncio
async def test_repository_error_is_absorbed() -> None:
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore(fail_record=True)  # record_queued raises StoreError
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise (StoreError absorbed)


@pytest.mark.asyncio
async def test_monitor_repo_error_still_promotes_completions_in_same_cycle() -> None:
    # Regression logic-download#2: if ``_reconcile_states`` raises ``StoreError`` (set_state
    # down on another hash), the old code set ``states={}`` then called ``_handle_completions``
    # → each shared hash → ``states.get(...) is None`` → ignored → NO completion recorded
    # in the whole cycle (latency +1 cycle although we already have the signal). The fix re-reads
    # ``read_tracked_states()`` BEFORE ``_handle_completions`` so the completions are seen.
    client = FakeDownloadClient(
        # _A completed: the completion must be recorded in this very cycle. _B is listed and
        # fails its set_state transition.
        listed=[(_status(_B), _status(_A, completed=True))],
    )
    downloads = FakeTrackedDownloadStore(fail_set_state_for={_B})
    # _A already DOWNLOADING (no transition by _reconcile_states); _B QUEUED → it will try
    # set_state(_B, DOWNLOADING) which raises → step 1 crashes, but _A is completed.
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.states[_B] = DownloadState.QUEUED
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)
    # _A's completion is recorded despite the failure of _reconcile_states on _B
    assert downloads.states[_A] is DownloadState.COMPLETED


@pytest.mark.asyncio
async def test_active_states_repo_failure_is_absorbed_at_step_2() -> None:
    # ``read_tracked_states`` that raises IN A LOOP (persistent store failure): step 1 absorbs, then
    # the re-read of step 2 (logic-download#2) absorbs in turn → the cycle ends without
    # crashing the loop (the next cycle will replay). We exercise HERE the branch
    # ``except StoreError`` of step 2 separately from that of step 1.
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore(fail_tracked_states=True)
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)  # does not raise (both StoreError are absorbed)


@pytest.mark.asyncio
async def test_one_hash_repo_failure_does_not_starve_other_completions() -> None:
    # Regression error-boundary#2: a ``StoreError`` in ``_record_completion`` of hash N
    # used to bubble up to the cycle handler, abandoning N+1, N+2 of the same snapshot. The fix
    # isolates PER HASH (try/except around _record_completion), honoring the "isolated per
    # step" intent of the comment (I2).
    client = FakeDownloadClient(
        listed=[
            (
                _status(_A, completed=True),
                _status(_B, completed=True),
            )
        ],
    )
    # _A and _B in DOWNLOADING; set_completed(_A, ...) crashes → _record_completion of _A
    # raises; _B must nonetheless be completed (intra-cycle continuity).
    downloads = FakeTrackedDownloadStore(fail_set_completed_for={_A})
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.states[_B] = DownloadState.DOWNLOADING
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_B] is DownloadState.COMPLETED  # despite the failure on _A


@pytest.mark.asyncio
async def test_intra_cycle_floor_accounts_for_links_added_this_cycle() -> None:
    # two candidates of 600 bytes, 1000 free: the 1st passes, the 2nd defers (600 + 600 > 1000).
    # A candidate admitted this cycle is not in amuled's queue yet, so the outstanding term is
    # carried IN MEMORY over the course of the cycle.
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_A, "062A"), _candidate(_B, "062A"))
    )
    observation_reader = FakeObservationReader(
        observations={
            _A: _observation(_A, "a", 600),
            _B: _observation(_B, "b", 600),
        }
    )
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1000,
        min_free=0,
    )
    await run_download_cycle(deps, _NODE)
    assert len(client.started) == 1  # only one fit above the floor


@pytest.mark.asyncio
async def test_candidate_for_unknown_target_is_treated_as_complete() -> None:
    # _target_status: a candidate whose target_id is ABSENT from _TARGETS → "complete"
    # (conservative) → SKIP_COMPLETE policy → no link, hash not enqueued.
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_A, "S9E999Z"),)  # ghost target, absent from _TARGETS
    )
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert client.started == []
    assert _A not in downloads.states


@pytest.mark.asyncio
async def test_monitor_no_op_when_state_already_matches() -> None:
    # _reconcile_states: in-progress entry (done=3/full=10) and repo already DOWNLOADING →
    # wanted_state is current → NO set_state (FALSE branch of `if current is not wanted_state`).
    client = FakeDownloadClient(listed=[(_status(_A, done=3, total=10),)])
    tracked_download_store = FakeNoSetStateTrackedDownloadStore()
    tracked_download_store.states[_A] = DownloadState.DOWNLOADING
    deps = _deps(
        client=client,
        downloads=tracked_download_store,
    )
    await run_download_cycle(deps, _NODE)
    assert tracked_download_store.states[_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_queued_download_without_observation_emits_no_link() -> None:
    # _start_unlisted: a QUEUED download without observation in the catalog → no start
    # (branch `if observation is None: continue`).
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.QUEUED
    downloads.sizes[_A] = 100
    deps = _deps(
        client=client,
        downloads=downloads,
        observation_reader=FakeObservationReader(observations={}),  # no observation
    )
    await run_download_cycle(deps, _NODE)
    assert client.started == []


@pytest.mark.asyncio
async def test_start_unreachable_keeps_queued_and_is_tolerated() -> None:
    # start raises ClientUnreachableError → tolerated at cycle level; the download stays QUEUED
    # (record_queued already happened) → caught up next round. write-before-network invariant.
    client = FakeDownloadClient(start_failures=[ClientUnreachableError("down")])
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise
    assert downloads.states[_A] is DownloadState.QUEUED  # stays queued → caught up
    assert client.started == []


@pytest.mark.asyncio
async def test_start_rejected_marks_failed_and_does_not_crash() -> None:
    # start raises DownloadRejectedError (the client refused the download):
    # THIS hash is marked FAILED (spec §9 "failed + log"), the loop continues, does not raise.
    client = FakeDownloadClient(start_failures=[DownloadRejectedError("rejected")])
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise (application failure tolerated per hash)
    assert downloads.states[_A] is DownloadState.FAILED  # link rejected → marked failed
    assert downloads.failures[_A] is FailureReason.REJECTED
    assert client.started == []


@pytest.mark.asyncio
async def test_start_rejected_for_one_file_does_not_block_the_next() -> None:
    # start rejected for _A, accepted for _B: _A → FAILED, _B → started and
    # stays QUEUED. The break does not abort the loop (continues to the next hash).
    client = FakeDownloadClient(start_failures=[DownloadRejectedError("rejected")])
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_A, "062A"), _candidate(_B, "062A"))
    )
    observation_reader = FakeObservationReader(
        observations={
            _A: _observation(_A, "a", 1),
            _B: _observation(_B, "b", 1),
        }
    )
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.FAILED  # rejected
    assert downloads.states[_B] is DownloadState.QUEUED  # accepted (link emitted)
    assert _B in _started(client)
    assert _A not in _started(client)


@pytest.mark.asyncio
async def test_completion_and_new_candidate_in_the_same_cycle() -> None:
    # _A completed via the SHARED files (recorded this cycle); _B is a new candidate
    # (queued + link).
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.sizes[_A] = 10
    decision_reader = FakeDecisionReader(candidates=(_candidate(_B, "062A"),))
    observation_reader = FakeObservationReader(observations={_B: _observation(_B, "b.avi", 100)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.COMPLETED  # shared and out of the queue
    assert downloads.states[_B] is DownloadState.QUEUED  # new → enqueued
    assert _B in _started(client)  # + link emitted


@pytest.mark.asyncio
async def test_emits_download_queued() -> None:
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(
        observations={_A: _observation(_A, "Keroro.avi", 100)}
    )
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    assert any(type(e).__name__ == "DownloadQueued" for e in event_emitter.events)
    assert event_emitter.node_ids == {_NODE}


@pytest.mark.asyncio
async def test_emits_download_completed() -> None:
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    downloads = FakeTrackedDownloadStore()
    downloads.record_queued(_key(_A), "062A", 100, FakeTime().wall.now())
    downloads.states[_A] = DownloadState.DOWNLOADING
    deps = _deps(
        client=client,
        downloads=downloads,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    completed = [e for e in event_emitter.events if isinstance(e, DownloadCompleted)]
    # No observation, no decision left: the hash names the file, the queued row its target.
    assert completed == [DownloadCompleted(_key(_A), _A, (TargetTitle("062A", "t"),))]
    assert event_emitter.node_ids == {_NODE}


@pytest.mark.asyncio
async def test_a_completion_names_the_clean_file_and_every_download_target_of_the_hash() -> None:
    targets = (
        TargetSegment(
            season=2, seasonal_number=11, absolute_number=62, letter="A", title="ta", status="lost"
        ),
        TargetSegment(
            season=2, seasonal_number=12, absolute_number=62, letter="B", title="tb", status="lost"
        ),
    )
    event_emitter = FakeEventEmitter()
    downloads = FakeTrackedDownloadStore()
    downloads.record_queued(_key(_A), "062A", 100, FakeTime().wall.now())
    downloads.states[_A] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_A, "062A"), _candidate(_A, "062B"), _candidate(_B, "063A"))
    )
    observation_reader = FakeObservationReader(
        observations={_A: _observation(_A, "Keroro Ã©.avi", 100)},
        best={_A: _observation(_A, "Keroro é.avi", 100)},
    )
    deps = _deps(
        client=FakeDownloadClient(listed=[(_status(_A, completed=True),)]),
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        event_emitter=event_emitter,
        targets=targets,
    )
    await run_download_cycle(deps, _NODE)
    completed = [e for e in event_emitter.events if isinstance(e, DownloadCompleted)]
    assert completed == [
        DownloadCompleted(
            _key(_A), "Keroro é.avi", (TargetTitle("062A", "ta"), TargetTitle("062B", "tb"))
        )
    ]


# ---------------------------------------------------------------------------
# I2: per-STEP error granularity (anti-starvation): a StoreError in one
# step (completions / new candidates) must NOT prevent the OTHER from running.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_repo_failure_does_not_starve_new_candidates() -> None:
    # _handle_completions raises StoreError (set_completed fails on the shared hash _A)
    # → _queue_new_candidates AND _start_unlisted run ANYWAY for _B:
    # a step-2 store failure does not starve step 3 (anti-starvation, I2).
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    downloads = FakeTrackedDownloadStore(fail_set_completed_for={_A})  # step 2 raises StoreError
    downloads.states[_A] = DownloadState.DOWNLOADING  # completed at step 2, which raises
    downloads.sizes[_A] = 10
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_B, "062A"),)  # new candidate step 3
    )
    observation_reader = FakeObservationReader(observations={_B: _observation(_B, "b.avi", 100)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise
    # Observable effect of step 3: _B enqueued AND its link emitted despite the step-2 failure.
    assert downloads.states[_B] is DownloadState.QUEUED
    assert _B in _started(client)
    # _A stays DOWNLOADING (the set_completed failure left step 2 incomplete → retry next round).
    assert downloads.states[_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_candidate_repo_failure_does_not_starve_completions() -> None:
    # Symmetric: _queue_new_candidates raises StoreError (record_queued fails) → the
    # step-2 completions were recorded ANYWAY (observable effect). The failure of
    # step 3 does not starve step 2.
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    downloads = FakeTrackedDownloadStore(fail_record=True)  # step 3 raises StoreError
    downloads.states[_A] = DownloadState.DOWNLOADING  # _A shared → completed step 2
    downloads.sizes[_A] = 10
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_B, "062A"),)  # new candidate → record_queued will raise
    )
    observation_reader = FakeObservationReader(observations={_B: _observation(_B, "b.avi", 100)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise
    # Observable effect of step 2: _A completed despite the step-3 failure.
    assert downloads.states[_A] is DownloadState.COMPLETED
    # _B was NOT enqueued (record_queued raised) → no link emitted for it.
    assert _B not in downloads.states
    assert client.started == []


@pytest.mark.asyncio
async def test_monitor_unreachable_aborts_subsequent_steps() -> None:
    # ClientUnreachableError at step 0 (downloads) = dead daemon → ABORT of the iteration:
    # neither the completions (step 2) nor the new candidates (step 3) must run.
    # (Doctrine "a dead daemon fails everything", distinct from StoreError isolation.)
    client = FakeDownloadClient(list_failures=[ClientUnreachableError("daemon down")])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.COMPLETED  # a pending completion (step 2)
    downloads.sizes[_A] = 10
    decision_reader = FakeDecisionReader(
        candidates=(_candidate(_B, "062A"),)  # a candidate (step 3)
    )
    observation_reader = FakeObservationReader(observations={_B: _observation(_B, "b.avi", 100)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise (tolerated) but EVERYTHING is skipped
    assert downloads.states[_A] is DownloadState.COMPLETED  # unchanged
    assert _B not in downloads.states  # step 3 NOT executed
    assert client.started == []


@pytest.mark.asyncio
async def test_monitor_repo_failure_is_isolated_and_does_not_starve_candidates() -> None:
    # _reconcile_states raises StoreError (set_state fails during reconciliation) → step 1 is
    # ISOLATED (log + continue), it does NOT starve step 3: _B is enqueued anyway.
    client = FakeDownloadClient(listed=[(_status(_A, done=10, total=10),)])
    downloads = FakeTrackedDownloadStore(fail_set_state_for={_A})
    downloads.states[_A] = DownloadState.QUEUED  # reconciled → set_state(DOWNLOADING) will raise
    decision_reader = FakeDecisionReader(candidates=(_candidate(_B, "062A"),))
    observation_reader = FakeObservationReader(observations={_B: _observation(_B, "b.avi", 100)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise
    # Step 3 ran despite the step-1 failure: _B enqueued + link emitted.
    assert downloads.states[_B] is DownloadState.QUEUED
    assert _B in _started(client)


@pytest.mark.asyncio
async def test_start_repo_failure_is_tolerated_and_does_not_raise() -> None:
    # _start_unlisted raises StoreError (set_state fails while marking a rejected start) →
    # tolerated (log), run_download_cycle does not raise. Contract "never raises".
    # start rejected → _start_unlisted tries set_state(FAILED), which raises
    # StoreError.
    client = FakeDownloadClient(start_failures=[DownloadRejectedError("rejected")])
    downloads = FakeTrackedDownloadStore(fail_set_state_for={_A})
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does NOT raise (step-4 StoreError tolerated)


# ---------------------------------------------------------------------------
# Completion via the EC SHARED files (positive signal).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shared_file_for_tracked_hash_is_completed() -> None:
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.COMPLETED


@pytest.mark.asyncio
async def test_shared_file_for_untracked_hash_is_ignored() -> None:
    downloads = FakeTrackedDownloadStore()  # _A not tracked by the crawler
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)
    assert _A not in downloads.states


@pytest.mark.asyncio
async def test_already_completed_shared_hash_is_not_recompleted() -> None:
    # A completed file stays in amuled's shared list forever. Without the terminal skip, every
    # cycle would re-stamp it and re-fire the community notification.
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.COMPLETED
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    deps = _deps(
        client=client,
        downloads=downloads,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.completed_at == {}
    assert not any(isinstance(e, DownloadCompleted) for e in event_emitter.events)


@pytest.mark.asyncio
async def test_failed_shared_hash_is_resurrected_and_notified() -> None:
    # The TTL can condemn a download that had in fact completed and been moved out of
    # IncomingDir. Finding it shared afterwards is amuled saying it exists: complete + notify.
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.FAILED
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    deps = _deps(
        client=client,
        downloads=downloads,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.COMPLETED
    assert any(isinstance(event, DownloadCompleted) for event in event_emitter.events)


@pytest.mark.asyncio
async def test_monitor_moves_queued_to_downloading_not_completed() -> None:
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.QUEUED
    client = FakeDownloadClient(listed=[(_status(_A, done=10, total=10),)])
    deps = _deps(
        client=client,
        downloads=downloads,
    )
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.DOWNLOADING  # NOT completed (bytes ignored)


@pytest.mark.asyncio
async def test_marks_seen_every_listed_download_completed_ones_included() -> None:
    # Stamping must happen BEFORE the TTL is evaluated.
    client = FakeDownloadClient(
        listed=[(_status(_A, done=3, total=10), _status(_B, completed=True))]
    )
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.states[_B] = DownloadState.COMPLETED
    deps = _deps(client=client, downloads=downloads)
    await run_download_cycle(deps, _NODE)
    assert downloads.seen == [{_A, _B}]


@pytest.mark.asyncio
async def test_a_download_amuled_no_longer_knows_becomes_failed() -> None:
    client, fake_time = FakeDownloadClient(listed=[(_status(_A),), ()]), FakeTime()
    logger = FakeLogger()
    downloads = FakeTrackedDownloadStore()
    downloads.record_queued(_key(_A), "062A", 1, fake_time.wall.now())
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "a", 1)})
    deps = _deps(
        client=client,
        downloads=downloads,
        observation_reader=observation_reader,
        lost_after=timedelta(hours=1),
        fake_time=fake_time,
        logger=logger,
    )
    await run_download_cycle(deps, _NODE)
    fake_time.advance(timedelta(hours=1))
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.FAILED
    assert downloads.failures[_A] is FailureReason.LOST
    assert deps.loss_deadline_by_file == {}
    assert client.started == []  # failed by the TTL: never started again
    assert LoggedLine("warning", f"file={_A} unseen by the client for 3600.0s: marked failed") in (
        logger.lines
    )


@pytest.mark.asyncio
async def test_each_download_write_carries_the_instant_read_right_before_it() -> None:
    wall_clock = FakeTickingWallClock(FakeTime())
    start = wall_clock.now()
    client = FakeDownloadClient(listed=[(_status(_A, completed=True),)])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(candidates=(_candidate(_B, "062A"),))
    observation_reader = FakeObservationReader(observations={_B: _observation(_B, "b.avi", 100)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    deps.wall_clock = wall_clock
    await run_download_cycle(deps, _NODE)
    minute = timedelta(minutes=1)
    assert downloads.completed_at == {_A: start + minute}
    assert downloads.seen_at == [start + 2 * minute]
    assert downloads.queued_at == {_B: start + 3 * minute}


@pytest.mark.asyncio
async def test_a_download_the_client_forgot_is_started_once_per_round_until_listed() -> None:
    # slskd drops every transfer on restart (stage 2, D13): absence restarts, a listing stops it.
    client = FakeDownloadClient(listed=[(), (), (_status(_A, done=1, total=9),), ()])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "a.avi", 9)})
    deps = _deps(client=client, downloads=downloads, observation_reader=observation_reader)
    rounds = []
    for _ in range(4):
        await run_download_cycle(deps, _NODE)
        rounds.append(len(client.started))
    assert rounds == [1, 2, 2, 3]
    assert client.started[0] == DownloadRequest(_key(_A), "a.avi", 9)
    assert downloads.states[_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_a_failed_or_completed_download_the_client_forgot_is_not_started() -> None:
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.FAILED
    downloads.states[_B] = DownloadState.COMPLETED
    observation_reader = FakeObservationReader(
        observations={_A: _observation(_A, "x", 1), _B: _observation(_B, "x", 1)}
    )
    await run_download_cycle(
        _deps(client=client, downloads=downloads, observation_reader=observation_reader), _NODE
    )
    assert client.started == []


@pytest.mark.asyncio
async def test_presence_repo_failure_is_absorbed_and_candidates_still_run() -> None:
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore(fail_set_seen=True)
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 100)})
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)  # does not raise
    assert downloads.states[_A] is DownloadState.QUEUED


@pytest.mark.asyncio
async def test_an_unmeasurable_output_directory_admits_nothing_and_does_not_raise() -> None:
    # A missing output mount must not take the crawler down: it also catalogues, which is the
    # primary mission. Refusing every candidate is the conservative degradation.
    client = FakeDownloadClient()
    downloads = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(observations={_A: _observation(_A, "x", 100)})
    event_emitter = FakeEventEmitter()
    deps = _deps(
        client=client,
        downloads=downloads,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        event_emitter=event_emitter,
    )
    deps.free_space_meter = FakeBrokenFreeSpaceMeter()
    await run_download_cycle(deps, _NODE)
    assert client.started == []
    assert _A not in downloads.states
    assert not [e for e in event_emitter.events if isinstance(e, FreeSpaceSampled | DiskSpaceLow)]


@pytest.mark.asyncio
async def test_each_cycle_reports_the_measured_free_space() -> None:
    event_emitter = FakeEventEmitter()
    deps = _deps(
        client=FakeDownloadClient(),
        downloads=FakeTrackedDownloadStore(),
        free=4_242,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    assert FreeSpaceSampled(free_bytes=4_242) in event_emitter.events


@pytest.mark.asyncio
async def test_low_disk_warns_once_per_crossing_and_rearms_at_the_floor() -> None:
    event_emitter = FakeEventEmitter()
    free_space_meter = FakeFreeSpaceMeter(500)
    deps = _deps(
        client=FakeDownloadClient(),
        downloads=FakeTrackedDownloadStore(),
        min_free=600,
        event_emitter=event_emitter,
    )
    deps.free_space_meter = free_space_meter
    warnings_per_cycle: list[int] = []
    for free in (500, 400, 600, 599):  # cross down, stay low, back AT the floor, cross again
        free_space_meter.free = free
        before = len(event_emitter.events)
        await run_download_cycle(deps, _NODE)
        warnings_per_cycle.append(
            sum(isinstance(e, DiskSpaceLow) for e in event_emitter.events[before:])
        )
    assert warnings_per_cycle == [1, 0, 0, 1]
    assert DiskSpaceLow(free_bytes=500, min_free_bytes=600) in event_emitter.events
    assert event_emitter.node_ids == {_NODE}


@pytest.mark.asyncio
async def test_a_failure_the_client_reports_stays_failed_round_after_round() -> None:
    # Stage 2, D12: an erroneous partfile is failed, and a listing without progress does not
    # flap it back to downloading each round.
    erroneous = _status(_A, done=3, total=10, failure=FailureReason.ERROR)
    client = FakeDownloadClient(listed=[(erroneous,)] * 3)
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    deps = _deps(client=client, downloads=downloads)
    rounds = []
    for _ in range(3):
        await run_download_cycle(deps, _NODE)
        rounds.append((downloads.states[_A], downloads.failures.get(_A)))
    assert rounds == [(DownloadState.FAILED, FailureReason.ERROR)] * 3
    assert client.started == []


@pytest.mark.asyncio
async def test_waiting_for_sources_is_not_failing_for_a_simulated_year(tmp_path: Path) -> None:
    # The real TTL of one day, a month between rounds, the client listing the download each one.
    fake_time = FakeTime()
    connection = open_local(tmp_path / "local.db")
    downloads = SqliteTrackedDownloadStore(connection)
    downloads.record_queued(_key(_A), "062A", 10, fake_time.wall.now())
    waiting = _status(_A, total=10, waiting=WaitingReason.NO_SOURCE)
    client = FakeDownloadClient(listed=[(waiting,)] * 12)
    deps = _deps(
        client=client,
        downloads=downloads,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    for _ in range(12):
        fake_time.advance(timedelta(days=30))
        await run_download_cycle(deps, _NODE)
    row = connection.execute("SELECT state, waiting_reason, failure_reason FROM downloads")
    assert row.fetchall() == [("downloading", "no_source", None)]
    connection.close()


@pytest.fixture
def real_downloads(tmp_path: Path) -> Iterator[SqliteTrackedDownloadStore]:
    connection = open_local(tmp_path / "local.db")
    yield SqliteTrackedDownloadStore(connection)
    connection.close()


@pytest.mark.asyncio
async def test_a_wall_clock_step_forward_fails_no_download_absent_from_one_poll(
    real_downloads: SqliteTrackedDownloadStore,
) -> None:
    fake_time = FakeTime()
    real_downloads.record_queued(_key(_A), "062A", 10, fake_time.wall.now())
    deps = _deps(
        client=FakeDownloadClient(listed=[(_status(_A, total=10),), ()]),
        downloads=real_downloads,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    fake_time.step_wall(timedelta(days=2))
    await run_download_cycle(deps, _NODE)
    assert real_downloads.read_tracked_states() == {_key(_A): DownloadState.DOWNLOADING}


@pytest.mark.asyncio
async def test_a_latest_seen_at_in_the_future_waits_lost_after_no_more(
    real_downloads: SqliteTrackedDownloadStore,
) -> None:
    # Stamped before the wall clock stepped back an hour, while the node was down.
    fake_time = FakeTime()
    real_downloads.record_queued(_key(_A), "062A", 10, fake_time.wall.now() + timedelta(hours=1))
    deps = _deps(
        client=FakeDownloadClient(),
        downloads=real_downloads,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    fake_time.advance(timedelta(days=1) - timedelta(seconds=1))
    await run_download_cycle(deps, _NODE)
    assert real_downloads.read_tracked_states() == {_key(_A): DownloadState.QUEUED}
    fake_time.advance(timedelta(seconds=1))
    await run_download_cycle(deps, _NODE)
    assert real_downloads.read_tracked_states() == {_key(_A): DownloadState.FAILED}


@pytest.mark.asyncio
async def test_a_download_last_seen_two_days_ago_fails_at_the_first_cycle(
    real_downloads: SqliteTrackedDownloadStore,
) -> None:
    fake_time = FakeTime()
    real_downloads.record_queued(_key(_A), "062A", 10, fake_time.wall.now() - timedelta(days=2))
    deps = _deps(
        client=FakeDownloadClient(),
        downloads=real_downloads,
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    assert real_downloads.read_tracked_states() == {_key(_A): DownloadState.FAILED}


@pytest.mark.asyncio
async def test_a_download_the_node_queued_is_lost_after_lost_after_of_monotonic_time(
    real_downloads: SqliteTrackedDownloadStore,
) -> None:
    fake_time = FakeTime()
    deps = _deps(
        client=FakeDownloadClient(),  # never lists it
        downloads=real_downloads,
        decision_reader=FakeDecisionReader(candidates=(_candidate(_A, "062A"),)),
        observation_reader=FakeObservationReader(observations={_A: _observation(_A, "a.avi", 10)}),
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    fake_time.step_wall(timedelta(days=2))
    await run_download_cycle(deps, _NODE)
    assert real_downloads.read_tracked_states() == {_key(_A): DownloadState.QUEUED}
    fake_time.advance(timedelta(days=1))
    await run_download_cycle(deps, _NODE)
    assert real_downloads.read_tracked_states() == {_key(_A): DownloadState.FAILED}


@pytest.mark.asyncio
async def test_a_duplicate_queuing_keeps_the_deadline_its_latest_seen_at_leaves() -> None:
    fake_time = FakeTime()
    downloads = FakeLaggingTrackedDownloadStore()
    downloads.record_queued(_key(_A), "062A", 10, fake_time.wall.now() - timedelta(hours=23))
    deps = _deps(
        client=FakeDownloadClient(),
        downloads=downloads,
        decision_reader=FakeDecisionReader(candidates=(_candidate(_A, "062A"),)),
        observation_reader=FakeObservationReader(observations={_A: _observation(_A, "a.avi", 10)}),
        lost_after=timedelta(days=1),
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    fake_time.advance(timedelta(hours=1))
    await run_download_cycle(deps, _NODE)
    assert downloads.states[_A] is DownloadState.FAILED


@pytest.mark.asyncio
async def test_a_row_the_operator_deleted_leaves_the_loss_deadlines() -> None:
    fake_time = FakeTime()
    downloads = FakeTrackedDownloadStore()
    downloads.record_queued(_key(_A), "062A", 10, fake_time.wall.now())
    deps = _deps(
        client=FakeDownloadClient(listed=[(_status(_A),), ()]),
        downloads=downloads,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    assert deps.loss_deadline_by_file == {_key(_A): fake_time.monotonic.now() + timedelta(days=1)}
    del downloads.states[_A]  # for a manual retry
    await run_download_cycle(deps, _NODE)
    assert deps.loss_deadline_by_file == {}


def _reading(name: str, role: SourceRole | None = SourceRole.QUEUED) -> SourceReading:
    return SourceReading(SourceKey(Network.ED2K, "1f" * 16), name, None, role, None, None, (), 0)


@pytest.mark.asyncio
async def test_the_sources_of_each_tracked_download_the_client_lists_are_recorded() -> None:
    # Stage 4, D8: the untracked C is not the crawler's, and each read_at precedes its read.
    fake_time = FakeTime()
    start = fake_time.wall.now()
    readings: dict[str, tuple[SourceReading, ...]] = {
        _A: (_reading("peer A"),),
        _B: (_reading("peer B", None),),
    }
    listed = (_status(_A), _status(_C), _status(_B))
    client = FakeDownloadClient(listed=[listed])
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.states[_B] = DownloadState.QUEUED
    sources = FakeSourcePointStore()
    deps = _deps(
        client=client,
        source_client=source_client,
        downloads=downloads,
        sources=sources,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    assert source_client.source_reads == [_A, _B]
    assert sources.recorded == [
        (_A, readings[_A], start),
        (_B, readings[_B], start + timedelta(seconds=1)),
    ]


@pytest.mark.asyncio
async def test_a_download_the_client_reports_completed_is_not_read() -> None:
    client = FakeDownloadClient(listed=[(_status(_A, completed=True), _status(_B))])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.states[_B] = DownloadState.DOWNLOADING
    source_client = FakeSourceClient()
    await run_download_cycle(
        _deps(client=client, source_client=source_client, downloads=downloads), _NODE
    )
    assert source_client.source_reads == [_B]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", _UNAVAILABLE, ids=["unreachable", "rejected"])
async def test_a_daemon_unavailable_while_reading_sources_ends_the_round_after_the_starts(
    failure: Exception,
) -> None:
    # The sources step only observes: it runs last, so its failure never skips a start.
    client = FakeDownloadClient(listed=[(_status(_A), _status(_B))])
    source_client = FakeSourceClient(source_failures=[failure])
    downloads = FakeTrackedDownloadStore()
    for native_id in (_A, _B):
        downloads.states[native_id] = DownloadState.DOWNLOADING
    downloads.states[_C] = DownloadState.QUEUED
    observation_reader = FakeObservationReader(observations={_C: _observation(_C, "c.avi", 1)})
    sources = FakeSourcePointStore()
    await run_download_cycle(
        _deps(
            client=client,
            source_client=source_client,
            downloads=downloads,
            observation_reader=observation_reader,
            sources=sources,
        ),
        _NODE,
    )  # does not raise
    assert _started(client) == [_C]
    assert source_client.source_reads == [_A]
    assert sources.recorded == []


@pytest.mark.asyncio
async def test_a_repo_failure_on_one_download_skips_its_sources_only() -> None:
    client = FakeDownloadClient(listed=[(_status(_A), _status(_B))])
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.states[_B] = DownloadState.DOWNLOADING
    sources = FakeSourcePointStore(fail_for={_A})
    await run_download_cycle(
        _deps(client=client, downloads=downloads, sources=sources),
        _NODE,
    )
    assert [file for file, *_ in sources.recorded] == [_B]


@pytest.mark.asyncio
async def test_a_repo_failure_reading_the_tracked_downloads_reads_no_source() -> None:
    client = FakeDownloadClient(listed=[(_status(_A),)])
    source_client = FakeSourceClient()
    downloads = FakeTrackedDownloadStore(fail_tracked_states=True)
    deps = _deps(client=client, source_client=source_client, downloads=downloads)
    await run_download_cycle(deps, _NODE)  # does not raise
    assert source_client.source_reads == []


@pytest.mark.asyncio
async def test_a_daemon_unreachable_at_the_start_reads_no_source() -> None:
    client = FakeDownloadClient(
        listed=[(_status(_A),)], start_failures=[ClientUnreachableError("down")]
    )
    downloads = FakeTrackedDownloadStore()
    downloads.states[_A] = DownloadState.DOWNLOADING
    downloads.states[_C] = DownloadState.QUEUED
    observation_reader = FakeObservationReader(observations={_C: _observation(_C, "c.avi", 1)})
    source_client = FakeSourceClient()
    deps = _deps(
        client=client,
        source_client=source_client,
        downloads=downloads,
        observation_reader=observation_reader,
    )
    await run_download_cycle(deps, _NODE)
    assert source_client.source_reads == []


@pytest.mark.asyncio
async def test_sources_are_read_once_per_interval_however_often_the_cycle_runs() -> None:
    # Source points spec, D3: rounds 30 s apart, sources every 300 s, the first round included.
    fake_time = FakeTime()
    start = fake_time.wall.now()
    client = FakeDownloadClient(listed=[(_status(_A),)] * 11)
    sources = FakeSourcePointStore()
    deps = _deps(
        client=client,
        downloads=_tracking(_A),
        sources=sources,
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    for _ in range(11):
        await run_download_cycle(deps, _NODE)
        fake_time.advance(timedelta(seconds=30))
    assert [read_at for _, _, read_at in sources.recorded] == [
        start,
        start + timedelta(seconds=300),
    ]


@pytest.mark.asyncio
async def test_a_sources_read_the_daemon_failed_waits_for_the_next_interval() -> None:
    # The step's time is taken when it starts, so an unreachable client is not retried each poll.
    fake_time = FakeTime()
    client = FakeDownloadClient(listed=[(_status(_A),)] * 3)
    source_client = FakeSourceClient(source_failures=[ClientUnreachableError("down")])
    deps = _deps(
        client=client,
        source_client=source_client,
        downloads=_tracking(_A),
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    await run_download_cycle(deps, _NODE)
    fake_time.advance(timedelta(seconds=30))
    await run_download_cycle(deps, _NODE)
    assert source_client.source_reads == [_A]
    fake_time.advance(timedelta(seconds=270))
    await run_download_cycle(deps, _NODE)
    assert source_client.source_reads == [_A, _A]


@pytest.mark.asyncio
async def test_a_wall_clock_step_back_delays_no_sources_read() -> None:
    fake_time = FakeTime()
    client = FakeDownloadClient(listed=[(_status(_A),)] * 2)
    source_client = FakeSourceClient()
    deps = _deps(
        client=client,
        source_client=source_client,
        downloads=_tracking(_A),
        fake_time=fake_time,
        sources_interval=timedelta(seconds=300),
    )
    await run_download_cycle(deps, _NODE)
    fake_time.step_wall(timedelta(hours=-1))
    fake_time.advance(timedelta(seconds=300))
    await run_download_cycle(deps, _NODE)
    assert source_client.source_reads == [_A, _A]


_PEER, _OTHER_PEER = SourceKey(Network.ED2K, "1f2e3d4c" * 4), SourceKey(Network.ED2K, "c" * 32)


def _tracking(*hashes: str) -> FakeTrackedDownloadStore:
    downloads = FakeTrackedDownloadStore()
    for native_id in hashes:
        downloads.states[native_id] = DownloadState.DOWNLOADING
    return downloads


@pytest.mark.asyncio
async def test_a_source_useful_on_two_files_in_one_round_is_new_once() -> None:
    # Stage 4, D9: the first file's event, named after its decision and best name.
    queued = (RecordedReading(_PEER, "AnimuseeFMR", SourceRole.QUEUED),)
    sources = FakeSourcePointStore(kept={_A: queued, _B: queued})
    decision_reader = FakeDecisionReader(candidates=(_candidate(_A, "062A"),))
    observation_reader = FakeObservationReader(best={_A: _observation(_A, "Keroro 062.avi", 1)})
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A), _status(_B))])
    deps = _deps(
        client=client,
        downloads=_tracking(_A, _B),
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        sources=sources,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [
        SourceFirstUseful(
            _PEER, "AnimuseeFMR", _key(_A), "Keroro 062.avi", (TargetTitle("062A", "t"),)
        )
    ]
    assert event_emitter.node_ids == {_NODE}


@pytest.mark.asyncio
async def test_a_source_useful_again_after_the_threshold_reappears() -> None:
    # Each file asks the history before the round's start, not before its own read.
    fake_time = FakeTime()
    start = fake_time.wall.now()
    history = {
        _PEER: EarlierPoints(has_useful_point=True, latest_known_at=start - timedelta(hours=13)),
        _OTHER_PEER: EarlierPoints(
            has_useful_point=True, latest_known_at=start - timedelta(seconds=30)
        ),
    }
    kept: dict[str, tuple[RecordedReading, ...]] = {
        _A: (RecordedReading(_OTHER_PEER, None, SourceRole.QUEUED),),
        _B: (RecordedReading(_PEER, "AnimuseeFMR", SourceRole.SENDING),),
    }
    sources = FakeSourcePointStore(kept=kept, history=history)
    downloads = FakeTrackedDownloadStore()
    downloads.record_queued(_key(_B), "063A", 100, start)  # queued for it, no decision left
    downloads.states.update({_A: DownloadState.DOWNLOADING, _B: DownloadState.DOWNLOADING})
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A), _status(_B))])
    deps = _deps(
        client=client,
        source_client=FakeSourceClient(fake_time=fake_time),
        downloads=downloads,
        sources=sources,
        event_emitter=event_emitter,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    assert sources.asked == [(_OTHER_PEER, start), (_PEER, start)]
    assert sources.node_ids == {_NODE}  # the round writes and reads the cycle's node's points
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [
        SourceReappeared(_PEER, "AnimuseeFMR", _key(_B), _B, (TargetTitle("063A", "t2"),), 46800.0)
    ]


@pytest.mark.asyncio
async def test_a_reading_without_a_source_id_raises_nothing() -> None:
    sources = FakeSourcePointStore(kept={_A: (RecordedReading(None, "peer", SourceRole.QUEUED),)})
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A),)])
    deps = _deps(
        client=client,
        downloads=_tracking(_A),
        sources=sources,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    assert sources.asked == []
    assert not any(
        isinstance(e, SourceFirstUseful | SourceReappeared) for e in event_emitter.events
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kept",
    [
        (),
        (RecordedReading(None, "peer", SourceRole.QUEUED),),
        (RecordedReading(_PEER, "peer", SourceRole.NOTHING_NEW),),
    ],
    ids=["none", "no-source-id", "not-useful"],
)
async def test_a_round_without_a_useful_reading_with_a_source_id_never_asks_for_the_baseline(
    kept: tuple[RecordedReading, ...],
) -> None:
    sources = FakeSourcePointStore(kept={_A: kept})
    client = FakeDownloadClient(listed=[(_status(_A),)])
    deps = _deps(client=client, downloads=_tracking(_A), sources=sources)
    await run_download_cycle(deps, _NODE)
    assert sources.baselines == []


@pytest.mark.asyncio
async def test_the_baseline_is_asked_once_per_round_against_its_start() -> None:
    fake_time = FakeTime()
    start = fake_time.wall.now()
    kept: dict[str, tuple[RecordedReading, ...]] = {
        _A: (RecordedReading(None, "peer", SourceRole.QUEUED),),
        _B: (RecordedReading(_PEER, "AnimuseeFMR", SourceRole.QUEUED),),
        _C: (RecordedReading(_OTHER_PEER, None, SourceRole.SENDING),),
    }
    sources = FakeSourcePointStore(kept=kept)
    client = FakeDownloadClient(listed=[(_status(_A), _status(_B), _status(_C))])
    deps = _deps(
        client=client,
        source_client=FakeSourceClient(fake_time=fake_time),
        downloads=_tracking(_A, _B, _C),
        sources=sources,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    assert sources.baselines == [start]


@pytest.mark.asyncio
async def test_a_repo_failure_asking_the_baseline_skips_that_downloads_alerts_only() -> None:
    queued = (RecordedReading(_PEER, "AnimuseeFMR", SourceRole.QUEUED),)
    sources = FakeSourcePointStore(kept={_A: queued, _B: queued}, baseline_failures=1)
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A), _status(_B))])
    deps = _deps(
        client=client,
        downloads=_tracking(_A, _B),
        sources=sources,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, _NODE)
    assert [file for file, *_ in sources.recorded] == [_A, _B]
    assert len(sources.baselines) == 2
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [SourceFirstUseful(_PEER, "AnimuseeFMR", _key(_B), _B, ())]


@pytest.mark.asyncio
@pytest.mark.parametrize("order", [(_A, _B), (_B, _A)], ids=["a-first", "b-first"])
async def test_the_first_recording_round_is_a_baseline(
    tmp_path: Path, order: tuple[str, str]
) -> None:
    # On a real catalog: two queued sources in the node's first round, a third in the next.
    catalog = open_catalog(tmp_path / "catalog.db")
    for native_id in order:
        insert_file(catalog, native_id)
    readings: dict[str, tuple[SourceReading, ...]] = {
        _A: (_peer(_PEER),),
        _B: (_peer(_OTHER_PEER),),
    }
    fake_time = FakeTime()
    rounds = [tuple(_status(h) for h in order)] * 2
    client = FakeDownloadClient(listed=rounds)
    event_emitter = FakeEventEmitter()
    deps = _deps(
        client=client,
        source_client=FakeSourceClient(readings=readings, fake_time=fake_time),
        downloads=_tracking(_A, _B),
        sources=SqliteSourcePointStore(catalog, timedelta(seconds=30)),
        event_emitter=event_emitter,
        fake_time=fake_time,
    )
    await run_download_cycle(deps, _NODE)
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == []
    assert source_variant_node_ids(catalog) == {_NODE}
    fake_time.advance(timedelta(seconds=30))
    third = SourceKey(Network.ED2K, "d" * 32)
    readings[_A] = (_peer(_PEER), _peer(third))
    await run_download_cycle(deps, _NODE)
    alerts = [
        e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)
    ]
    assert alerts == [SourceFirstUseful(third, "peer", _key(_A), _A, ())]
    catalog.close()


def _peer(key: SourceKey, role: SourceRole = SourceRole.QUEUED) -> SourceReading:
    return SourceReading(key, "peer", None, role, None, None, (), 0)


@pytest.fixture
def real_catalog(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    catalog = open_catalog(tmp_path / "catalog.db")
    insert_file(catalog, _A)
    yield catalog
    catalog.close()


def _real_deps(
    catalog: sqlite3.Connection,
    client: FakeDownloadClient,
    source_client: FakeSourceClient,
    event_emitter: FakeEventEmitter,
    fake_time: FakeTime,
) -> DownloadDeps:
    """``_A`` tracked, its sources written to a real catalog."""
    sources = SqliteSourcePointStore(catalog, timedelta(seconds=30))
    return _deps(
        client=client,
        source_client=source_client,
        downloads=_tracking(_A),
        sources=sources,
        event_emitter=event_emitter,
        fake_time=fake_time,
    )


def _alerts(event_emitter: FakeEventEmitter) -> list[object]:
    return [e for e in event_emitter.events if isinstance(e, SourceFirstUseful | SourceReappeared)]


@pytest.mark.asyncio
async def test_a_source_useful_at_three_consecutive_reads_is_new_once(
    real_catalog: sqlite3.Connection,
) -> None:
    # From its second read on, its earlier useful point is recent: no event (D5).
    readings: dict[str, tuple[SourceReading, ...]] = {_A: (_peer(_OTHER_PEER),)}
    fake_time, event_emitter = FakeTime(), FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A),)] * 4)
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    deps = _real_deps(real_catalog, client, source_client, event_emitter, fake_time)
    await run_download_cycle(deps, _NODE)  # the node's first round, a baseline
    readings[_A] = (_peer(_OTHER_PEER), _peer(_PEER))
    for _ in range(3):
        fake_time.advance(timedelta(seconds=30))
        await run_download_cycle(deps, _NODE)
    assert _alerts(event_emitter) == [SourceFirstUseful(_PEER, "peer", _key(_A), _A, ())]


@pytest.mark.asyncio
async def test_a_source_back_after_13_hours_through_an_undetermined_read_reappears(
    real_catalog: sqlite3.Connection,
) -> None:
    # An unknown point does not end an absence (stage 4, D9).
    readings: dict[str, tuple[SourceReading, ...]] = {_A: (_peer(_PEER),)}
    fake_time, event_emitter = FakeTime(), FakeEventEmitter()
    client = FakeDownloadClient(listed=[(_status(_A),)] * 3)
    source_client = FakeSourceClient(readings=readings, fake_time=fake_time)
    deps = _real_deps(real_catalog, client, source_client, event_emitter, fake_time)
    last_useful = fake_time.wall.now()
    await run_download_cycle(deps, _NODE)
    fake_time.advance(timedelta(hours=13))
    readings[_A] = (_peer(_PEER, SourceRole.UNDETERMINED),)
    await run_download_cycle(deps, _NODE)
    fake_time.advance(timedelta(seconds=30))
    readings[_A] = (_peer(_PEER),)
    absent = (fake_time.wall.now() - last_useful).total_seconds()
    await run_download_cycle(deps, _NODE)
    assert _alerts(event_emitter) == [SourceReappeared(_PEER, "peer", _key(_A), _A, (), absent)]
