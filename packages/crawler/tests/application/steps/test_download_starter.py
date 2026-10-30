import pytest

from catalog_matching.domain.identifiers import TargetId
from p2pwatch.domain.client_errors import DownloadRejectedError
from p2pwatch.domain.download.request import DownloadRequest
from p2pwatch.domain.download.states import DownloadState, FailureReason
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_cycle import (
    HASH_A,
    HASH_B,
    NODE_ID,
    build_cycle,
    candidate,
    key,
    observation,
    started,
    status,
)


@pytest.mark.asyncio
async def test_queued_download_without_observation_emits_no_link() -> None:
    # start_unlisted: a QUEUED download without observation in the catalog → no start
    # (branch `if observation is None: continue`).
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.QUEUED
    tracked_download_store.sizes[HASH_A] = 100
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        observation_reader=FakeObservationReader(observations={}),  # no observation
    )
    await cycle.run(NODE_ID)
    assert client.started == []


@pytest.mark.asyncio
async def test_start_rejected_marks_failed_and_does_not_crash() -> None:
    # start raises DownloadRejectedError (the client refused the download):
    # THIS hash is marked FAILED (spec §9 "failed + log"), the loop continues, does not raise.
    client = FakeDownloadClient(start_failures=[DownloadRejectedError("rejected")])
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
    await cycle.run(NODE_ID)  # does not raise (application failure tolerated per hash)
    assert (
        tracked_download_store.states[HASH_A] is DownloadState.FAILED
    )  # link rejected → marked failed
    assert tracked_download_store.failures[HASH_A] is FailureReason.REJECTED
    assert client.started == []


@pytest.mark.asyncio
async def test_start_rejected_for_one_file_does_not_block_the_next() -> None:
    # start rejected for HASH_A, accepted for HASH_B: HASH_A → FAILED, HASH_B → started and
    # stays QUEUED. The break does not abort the loop (continues to the next hash).
    client = FakeDownloadClient(start_failures=[DownloadRejectedError("rejected")])
    tracked_download_store = FakeTrackedDownloadStore()
    decision_reader = FakeDecisionReader(
        candidates=(
            candidate(HASH_A, target_id=TargetId("062A")),
            candidate(HASH_B, target_id=TargetId("062A")),
        )
    )
    observation_reader = FakeObservationReader(
        observations={
            HASH_A: observation(HASH_A, filename="a", size_bytes=1),
            HASH_B: observation(HASH_B, filename="b", size_bytes=1),
        }
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
    )
    await cycle.run(NODE_ID)
    assert tracked_download_store.states[HASH_A] is DownloadState.FAILED  # rejected
    assert tracked_download_store.states[HASH_B] is DownloadState.QUEUED  # accepted (link emitted)
    assert HASH_B in started(client)
    assert HASH_A not in started(client)


@pytest.mark.asyncio
async def test_a_download_the_client_forgot_is_started_once_per_round_until_listed() -> None:
    # slskd drops every transfer on restart (stage 2, D13): absence restarts, a listing stops it.
    client = FakeDownloadClient(listed=[(), (), (status(HASH_A, done=1, total=9),), ()])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, filename="a.avi", size_bytes=9)}
    )
    cycle = build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        observation_reader=observation_reader,
    )
    rounds = []
    for _ in range(4):
        await cycle.run(NODE_ID)
        rounds.append(len(client.started))
    assert rounds == [1, 2, 2, 3]
    assert client.started[0] == DownloadRequest(file=key(HASH_A), filename="a.avi", size_bytes=9)
    assert tracked_download_store.states[HASH_A] is DownloadState.DOWNLOADING


@pytest.mark.asyncio
async def test_a_failed_or_completed_download_the_client_forgot_is_not_started() -> None:
    client = FakeDownloadClient()
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.states[HASH_A] = DownloadState.FAILED
    tracked_download_store.states[HASH_B] = DownloadState.COMPLETED
    observation_reader = FakeObservationReader(
        observations={
            HASH_A: observation(HASH_A, filename="x", size_bytes=1),
            HASH_B: observation(HASH_B, filename="x", size_bytes=1),
        }
    )
    await build_cycle(
        client=client,
        tracked_download_store=tracked_download_store,
        observation_reader=observation_reader,
    ).run(NODE_ID)
    assert client.started == []
