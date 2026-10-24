from catalog_matching.domain.models import TargetSegment
from p2pwatch.application.steps.download_labeler import DownloadLabeler
from p2pwatch.domain.observability.events import TargetTitle
from tests.fakes.adapters.driven.fake_decision_reader import FakeDecisionReader
from tests.fakes.adapters.driven.fake_observation_reader import FakeObservationReader
from tests.fakes.adapters.driven.fake_time import FakeTime
from tests.fakes.adapters.driven.fake_tracked_download_store import FakeTrackedDownloadStore
from tests.support.application.steps.download_deps import (
    HASH_A,
    HASH_B,
    candidate,
    key,
    observation,
)

_TARGETS = (
    TargetSegment(
        season=2, seasonal_number=11, absolute_number=62, letter="A", title="ta", status="lost"
    ),
    TargetSegment(
        season=2, seasonal_number=12, absolute_number=62, letter="B", title="tb", status="lost"
    ),
)


def _labeler(
    *,
    decision_reader: FakeDecisionReader | None = None,
    observation_reader: FakeObservationReader | None = None,
    tracked_download_store: FakeTrackedDownloadStore | None = None,
) -> DownloadLabeler:
    return DownloadLabeler(
        observation_reader=observation_reader or FakeObservationReader(),
        decision_reader=decision_reader or FakeDecisionReader(),
        tracked_download_reader=tracked_download_store or FakeTrackedDownloadStore(),
        targets=_TARGETS,
    )


def test_the_best_filename_is_the_clean_one() -> None:
    observation_reader = FakeObservationReader(
        observations={HASH_A: observation(HASH_A, "Keroro Ã©.avi", 100)},
        best={HASH_A: observation(HASH_A, "Keroro é.avi", 100)},
    )
    labeler = _labeler(observation_reader=observation_reader)
    assert labeler.best_filename(key(HASH_A)) == "Keroro é.avi"


def test_a_file_whose_observations_are_gone_is_named_by_its_native_id() -> None:
    assert _labeler().best_filename(key(HASH_A)) == HASH_A


def test_the_titles_are_every_download_target_of_the_file() -> None:
    decision_reader = FakeDecisionReader(
        candidates=(candidate(HASH_A, "062A"), candidate(HASH_A, "062B"), candidate(HASH_B, "063A"))
    )
    labeler = _labeler(decision_reader=decision_reader)
    assert labeler.target_titles(key(HASH_A)) == (
        TargetTitle("062A", "ta"),
        TargetTitle("062B", "tb"),
    )


def test_a_file_without_a_download_decision_has_the_target_it_was_queued_for() -> None:
    tracked_download_store = FakeTrackedDownloadStore()
    tracked_download_store.record_queued(key(HASH_A), "062B", 100, FakeTime().wall.now())
    labeler = _labeler(tracked_download_store=tracked_download_store)
    assert labeler.target_titles(key(HASH_A)) == (TargetTitle("062B", "tb"),)


def test_a_target_the_targets_no_longer_list_has_an_empty_title() -> None:
    decision_reader = FakeDecisionReader(candidates=(candidate(HASH_A, "063A"),))
    labeler = _labeler(decision_reader=decision_reader)
    assert labeler.target_titles(key(HASH_A)) == (TargetTitle("063A", ""),)


def test_a_file_neither_decided_nor_queued_has_no_title() -> None:
    assert _labeler().target_titles(key(HASH_A)) == ()
