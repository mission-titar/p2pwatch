import pytest

from catalog_matching.domain.identifiers import TargetId
from catalog_matching.domain.models import TargetSegment
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.observability.node_metric import NodeCounter, NodeGauge, NodeMetricSample
from p2pwatch.domain.observability.notification import RelayedLogLine
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_free_space_meter import FakeFreeSpaceMeter
from tests.fakes.adapters.driven.fake_logger import LoggedLine
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_cycle import (
    HASH_A,
    HASH_B,
    NODE,
    build_cycle,
    candidate,
    key,
    observation,
    started,
    status,
)
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes


@pytest.mark.asyncio
async def test_new_candidate_is_queued_and_link_added() -> None:
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, TargetId("062A")),))
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, "Keroro.avi", 100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run(NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.QUEUED
    assert client.started == [DownloadRequest(key(HASH_A), "Keroro.avi", 100)]


@pytest.mark.asyncio
async def test_already_downloaded_candidate_is_deduped() -> None:
    client = FakeDownloadClient(listed=[(status(HASH_A),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING  # already known
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, TargetId("062A")),))
    observation_reader = FakeObservationReader(observations={HASH_A: observation(HASH_A, "x", 1)})
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run(NODE)
    assert client.started == []  # dedup: no new link


@pytest.mark.asyncio
async def test_two_segment_candidates_same_hash_dedup_to_one_download() -> None:
    # spec §8: a whole-episode file yields BOTH (hash,062A) and (hash,062B) in
    # read_download_candidates; is_tracked(hash) dedups them to ONE physical download.
    #
    # Both targets are DOWNLOAD-eligible ("lost", not "complete") so the ONLY thing that
    # can collapse the two candidates is the `is_tracked(hash)` guard in
    # queue_new_candidates, never `_target_status` falling back to its "complete"
    # default for an absent target (that would be an unrelated skip path, spec §6).
    targets = (
        TargetSegment(
            season=2, seasonal_number=11, absolute_number=62, letter="A", title="t", status="lost"
        ),
        TargetSegment(
            season=2, seasonal_number=12, absolute_number=62, letter="B", title="t", status="lost"
        ),
    )
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, TargetId("062A")), candidate(HASH_A, TargetId("062B")))
    )
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, "Keroro 062.avi", 100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        observability_dispatcher=observability.dispatcher,
        targets=targets,
    )
    await cycle.run(NODE)
    assert list(tracked_download_store.states) == [HASH_A]
    assert tracked_download_store.states[HASH_A] is DownloadState.QUEUED
    assert started(client) == [HASH_A]
    # Load-bearing assertion: exactly ONE DownloadQueued line. queue_new_candidates
    # dispatches one per NON-skipped candidate (download_decider.py, end of the loop body);
    # both candidates are policy-eligible here, so a SECOND line would only appear if the
    # `is_tracked` continue-guard were removed, unlike the hash-keyed dict observables
    # above (states/started), which stay collapsed regardless.
    queued_lines = [line for line in observability.logger.lines if "queued" in line.message]
    assert queued_lines == [LoggedLine("info", "download queued: 062A")]


@pytest.mark.asyncio
async def test_complete_target_candidate_is_skipped() -> None:
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_B, TargetId("063A")),)  # 063A status=complete
    )
    observation_reader = FakeObservationReader(observations={HASH_B: observation(HASH_B, "x", 1)})
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run(NODE)
    assert client.started == []
    assert HASH_B not in tracked_download_store.states


@pytest.mark.asyncio
async def test_a_candidate_that_would_break_the_disk_floor_defers() -> None:
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, TargetId("062A")),))
    observation_reader = FakeObservationReader(observations={HASH_A: observation(HASH_A, "x", 500)})
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1_000,
        min_free=600,  # 1000 - 500 < 600 → defers
    )
    await cycle.run(NODE)
    assert client.started == []
    assert HASH_A not in tracked_download_store.states


@pytest.mark.asyncio
async def test_outstanding_queue_bytes_are_charged_against_the_floor() -> None:
    # Free space alone would admit this candidate; the 900 bytes amuled still has to fetch
    # for a download already running is what refuses it.
    client = FakeDownloadClient(listed=[(status(HASH_B, done=100, total=1000),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_B] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, TargetId("062A")),))
    observation_reader = FakeObservationReader(observations={HASH_A: observation(HASH_A, "x", 200)})
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1_000,
        min_free=0,
    )
    await cycle.run(NODE)
    assert client.started == []
    assert HASH_A not in tracked_download_store.states


@pytest.mark.asyncio
async def test_a_nascent_queue_entry_commits_nothing() -> None:
    # size_full == 0: amuled does not know the total yet. Charging size_full - size_done would
    # be NEGATIVE and invent free space, so the entry contributes zero and the candidate fits.
    client = FakeDownloadClient(listed=[(status(HASH_B, done=50, total=0),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_B] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, TargetId("062A")),))
    observation_reader = FakeObservationReader(observations={HASH_A: observation(HASH_A, "x", 200)})
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1_000,
        min_free=800,
    )
    await cycle.run(NODE)
    assert tracked_download_store.states[HASH_A] is DownloadState.QUEUED


@pytest.mark.asyncio
async def test_candidate_without_observation_is_skipped() -> None:
    # a candidate for which no observation survived (edge case) cannot build a link:
    # we skip it (log), never a crash.
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, TargetId("062A")),))
    observation_reader = FakeObservationReader(observations={})
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run(NODE)
    assert client.started == []


@pytest.mark.asyncio
async def test_intra_cycle_floor_accounts_for_links_added_this_cycle() -> None:
    # two candidates of 600 bytes, 1000 free: the 1st passes, the 2nd defers (600 + 600 > 1000).
    # A candidate admitted this cycle is not in amuled's queue yet, so the outstanding term is
    # carried IN MEMORY over the course of the cycle.
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, TargetId("062A")), candidate(HASH_B, TargetId("062A")))
    )
    observation_reader = FakeObservationReader(
        observations={
            HASH_A: observation(HASH_A, "a", 600),
            HASH_B: observation(HASH_B, "b", 600),
        }
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        free=1000,
        min_free=0,
    )
    await cycle.run(NODE)
    assert len(client.started) == 1  # only one fit above the floor


@pytest.mark.asyncio
async def test_candidate_for_unknown_target_is_treated_as_complete() -> None:
    # _target_status: a candidate whose target_id is ABSENT from TARGETS → "complete"
    # (conservative) → SKIP_COMPLETE policy → no link, hash not enqueued.
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, TargetId("S9E999Z")),)  # ghost target, absent from TARGETS
    )
    observation_reader = FakeObservationReader(observations={HASH_A: observation(HASH_A, "x", 1)})
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run(NODE)
    assert client.started == []
    assert HASH_A not in tracked_download_store.states


@pytest.mark.asyncio
async def test_dispatches_download_queued() -> None:
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, TargetId("062A")),))
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, "Keroro.avi", 100)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        observability_dispatcher=observability.dispatcher,
    )
    await cycle.run(NODE)
    assert LoggedLine("info", "download queued: 062A") in observability.logger.lines
    assert NodeMetricSample(NodeCounter.DOWNLOADS_QUEUED, (), 1.0) in (
        observability.node_metric_store.read_samples()
    )


@pytest.mark.asyncio
async def test_each_cycle_reports_the_measured_free_space() -> None:
    observability = ObservabilityOverFakes()
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        free=4_242,
        observability_dispatcher=observability.dispatcher,
    )
    await cycle.run(NODE)
    assert observability.node_metric_store.read_samples() == (
        NodeMetricSample(NodeGauge.DISK_FREE_BYTES, (), 4_242.0),
    )


@pytest.mark.asyncio
async def test_low_disk_warns_once_per_crossing_and_rearms_at_the_floor() -> None:
    observability = ObservabilityOverFakes()
    free_space_meter = FakeFreeSpaceMeter(500)
    cycle = build_cycle(
        client=FakeDownloadClient(),
        tracked_download_store=FakeTrackedDownloadStore(),
        free_space_meter=free_space_meter,
        min_free=600,
        observability_dispatcher=observability.dispatcher,
    )
    warnings_per_cycle: list[int] = []
    for free in (500, 400, 600, 599):  # cross down, stay low, back AT the floor, cross again
        free_space_meter.free = free
        before = len(observability.notifier.calls)
        await cycle.run(NODE)
        warnings_per_cycle.append(len(observability.notifier.calls) - before)
    assert warnings_per_cycle == [1, 0, 0, 1]
    low = "download disk low: 0.0 GiB free, under the 0.0 GiB floor (no new download)"
    relayed = (Audience.OPERATIONS, RelayedLogLine(low, Severity.WARNING, NODE))
    assert observability.notifier.calls == [relayed, relayed]
