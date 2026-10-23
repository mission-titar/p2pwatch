import pytest

from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.steps.download_cycle import run_download_cycle
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.observability.events import DownloadCompleted, TargetTitle
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
from tests.fakes.adapters.driven.fake_event_emitter import FakeEventEmitter
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
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


@pytest.mark.asyncio
async def test_emits_download_completed() -> None:
    event_emitter = FakeEventEmitter()
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.record_queued(key(HASH_A), "062A", 100, FakeTime().wall.now())
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        event_emitter=event_emitter,
    )
    await run_download_cycle(deps, NODE)
    completed = [e for e in event_emitter.events if isinstance(e, DownloadCompleted)]
    # No observation, no decision left: the hash names the file, the queued row its target.
    assert completed == [DownloadCompleted(key(HASH_A), HASH_A, (TargetTitle("062A", "t"),))]
    assert event_emitter.node_ids == {NODE}


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
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.record_queued(key(HASH_A), "062A", 100, FakeTime().wall.now())
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, "062A"), candidate(HASH_A, "062B"), candidate(HASH_B, "063A"))
    )
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, "Keroro Ã©.avi", 100)},
        best={HASH_A: observation(HASH_A, "Keroro é.avi", 100)},
    )
    deps = build_deps(
        client=FakeDownloadClient(listed=[(status(HASH_A, completed=True),)]),
        tracked_download_store=tracked_download_store,
        decision_reader=decision_reader,
        observation_reader=observation_reader,
        event_emitter=event_emitter,
        targets=targets,
    )
    await run_download_cycle(deps, NODE)
    completed = [e for e in event_emitter.events if isinstance(e, DownloadCompleted)]
    assert completed == [
        DownloadCompleted(
            key(HASH_A), "Keroro é.avi", (TargetTitle("062A", "ta"), TargetTitle("062B", "tb"))
        )
    ]
