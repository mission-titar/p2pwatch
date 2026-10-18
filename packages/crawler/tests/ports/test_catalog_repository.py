from collections.abc import Iterator
from datetime import UTC, datetime

from catalog_matching.domain.engine import DecisionRecord, Explanation, MatchDecision
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.observation import FileObservation
from p2pwatch.ports.catalog_repository import (
    CatalogRepository,
    DownloadCandidate,
    ObservedFile,
    ReevalRow,
)

_KEY = FileKey(Network.ED2K, "31d6cfe0d16ae931b73c59d7e0c089c0")
_T0 = datetime(2026, 6, 12, tzinfo=UTC)


class _StubRepository:
    """Minimal structural implementation: satisfies CatalogRepository WITHOUT importing it."""

    def __init__(self) -> None:
        self.observations: list[tuple[FileObservation, datetime]] = []
        self.decisions: list[tuple[FileKey, MatchDecision, datetime]] = []
        self.retractions: list[tuple[FileKey, str, datetime]] = []

    def record_observation(self, observation: FileObservation, observed_at: datetime) -> None:
        self.observations.append((observation, observed_at))

    def record_decision(self, file: FileKey, decision: MatchDecision, decided_at: datetime) -> None:
        self.decisions.append((file, decision, decided_at))

    def record_retraction(self, file: FileKey, target_id: str, decided_at: datetime) -> None:
        self.retractions.append((file, target_id, decided_at))

    def latest_decisions(self, file: FileKey) -> dict[str, DecisionRecord]:
        return {}

    def download_candidates(self) -> tuple[DownloadCandidate, ...]:
        return ()

    def latest_observation(self, file: FileKey) -> ObservedFile | None:
        return None

    def best_observation(self, file: FileKey) -> ObservedFile | None:
        return None

    def known_filenames(self, file: FileKey) -> tuple[str, ...]:
        return ()

    def count_files(self) -> int:
        return 1

    def iter_reevaluation_rows(self) -> Iterator[ReevalRow]:
        return iter(
            (
                ReevalRow(
                    file=_KEY,
                    filename="Keroro 062A.avi",
                    size_bytes=100,
                    duration_seconds=None,
                    bitrate_kbps=None,
                ),
            )
        )


def test_protocol_is_satisfied_structurally() -> None:
    stub = _StubRepository()
    repository: CatalogRepository = stub  # mypy proves the structural satisfaction
    observation = FileObservation(
        file=_KEY,
        filename="Keroro 062A.avi",
        size_bytes=100,
        source_count=1,
        keyword="keroro",
    )
    decision = MatchDecision(
        target_id="062A",
        rule_name="exact",
        tier="download",
        explanation=Explanation(
            target_id="062A", rules_fired=("exact",), tokens_matched=(), coverage_values=()
        ),
    )
    repository.record_observation(observation, _T0)
    repository.record_decision(_KEY, decision, _T0)
    repository.record_retraction(_KEY, "062A", _T0)
    assert repository.latest_decisions(_KEY) == {}
    assert repository.download_candidates() == ()
    assert repository.latest_observation(_KEY) is None
    assert repository.best_observation(_KEY) is None
    assert repository.known_filenames(_KEY) == ()
    assert repository.count_files() == 1
    assert tuple(repository.iter_reevaluation_rows()) == (
        ReevalRow(
            file=_KEY,
            filename=observation.filename,
            size_bytes=observation.size_bytes,
            duration_seconds=None,
            bitrate_kbps=None,
        ),
    )
    assert stub.observations == [(observation, _T0)]
    assert stub.decisions == [(_KEY, decision, _T0)]
    assert stub.retractions == [(_KEY, "062A", _T0)]
