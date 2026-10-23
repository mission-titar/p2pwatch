import pytest

from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.steps.download_cycle import run_download_cycle
from p2pwatch.domain.download.states import DownloadState
from p2pwatch.domain.observability.notification import TextNotification
from p2pwatch.domain.observability.policy import Audience
from p2pwatch.domain.observability.severity import Severity
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_download_client import FakeDownloadClient
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
from tests.support.application.steps.observability_dispatcher import ObservabilityOverFakes


@pytest.mark.asyncio
async def test_dispatches_download_completed() -> None:
    observability = ObservabilityOverFakes()
    client = FakeDownloadClient(listed=[(status(HASH_A, completed=True),)])
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.record_queued(key(HASH_A), "062A", 100, FakeTime().wall.now())
    tracked_download_store.states[HASH_A] = DownloadState.DOWNLOADING
    deps = build_deps(
        client=client,
        tracked_download_store=tracked_download_store,
        observability_dispatcher=observability.dispatcher,
    )
    await run_download_cycle(deps, NODE)
    # No observation, no decision left: the hash names the file, the queued row its target.
    assert observability.notifier.calls == [
        (
            Audience.COMMUNITY,
            TextNotification(
                "✅ Downloaded",
                f"**Targets**\n062A - t\n\n**File**\n`{HASH_A}`",
                Severity.SUCCESS,
                NODE,
            ),
        )
    ]


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
    observability = ObservabilityOverFakes()
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
        observability_dispatcher=observability.dispatcher,
        targets=targets,
    )
    await run_download_cycle(deps, NODE)
    [(_, notification)] = observability.notifier.calls
    assert isinstance(notification, TextNotification)
    assert notification.body == "**Targets**\n062A - ta\n062B - tb\n\n**File**\n`Keroro é.avi`"
