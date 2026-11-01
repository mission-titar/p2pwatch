"""The promise of the ``DecisionReader`` and ``DecisionWriter`` pair."""

from abc import ABC, abstractmethod
from random import Random

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.application.ports.driven.decision_reader import DecisionReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.domain.download.candidate import DownloadCandidate
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import Retraction
from tests.support.domain.file_target_decision import (
    draw_dated_decision,
    draw_decision_record,
    draw_target_id,
    draw_target_ids,
)
from tests.support.domain.observation import draw_file, draw_file_observation
from tests.support.draws import draw_instants


def _draw_observed_file(randomness: Random, *, observation_writer: ObservationWriter) -> FileKey:
    file = draw_file(randomness)
    observation_writer.record_observation(
        draw_file_observation(randomness, file=file, has_media=True)
    )
    return file


class DecisionStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def observation_writer(self) -> ObservationWriter:
        """The writer of the observations of the writer's catalog."""

    @pytest.fixture
    @abstractmethod
    def writer(self) -> DecisionWriter:
        """The writer of a catalog holding no observation and no decision yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> DecisionReader:
        """The reader of the writer's catalog."""

    def test_a_file_never_decided_has_no_decision_and_no_candidate(
        self, *, randomness: Random, observation_writer: ObservationWriter, reader: DecisionReader
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        assert reader.read_latest_decisions(file) == {}
        assert reader.read_latest_decisions(draw_file(randomness)) == {}
        assert reader.read_download_candidates() == ()

    @pytest.mark.parametrize("tier", list(DecisionTier), ids=str)
    def test_a_decision_is_read_back_as_its_target_s_latest(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
        tier: DecisionTier,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        record = draw_decision_record(randomness, tier=tier)
        writer.record_decision(draw_dated_decision(randomness, file=file, decision=record))
        assert reader.read_latest_decisions(file) == {record.target_id: record}

    def test_a_target_s_latest_decision_is_the_most_recent_of_its_file_not_the_last_recorded(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
    ) -> None:
        file, other_file = (
            _draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(2)
        )
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        earlier_at, later_at, latest_at = draw_instants(randomness, count=3)
        latest = draw_decision_record(randomness, tier=DecisionTier.DOWNLOAD, target_id=target_id)
        earlier = draw_decision_record(randomness, tier=DecisionTier.CATALOG, target_id=target_id)
        other_target = draw_decision_record(
            randomness, tier=DecisionTier.NOTIFY, target_id=other_target_id
        )
        for decided_file, decision, decided_at in (
            (file, latest, later_at),
            (file, earlier, earlier_at),
            (file, other_target, earlier_at),
            (other_file, earlier, latest_at),
        ):
            writer.record_decision(
                draw_dated_decision(
                    randomness, file=decided_file, decision=decision, decided_at=decided_at
                )
            )
        assert reader.read_latest_decisions(file) == {
            target_id: latest,
            other_target_id: other_target,
        }

    def test_a_later_retraction_is_its_target_s_latest_decision_and_no_candidate(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        earlier_at, later_at = draw_instants(randomness, count=2)
        record = draw_decision_record(randomness, tier=DecisionTier.DOWNLOAD)
        retraction = Retraction(target_id=record.target_id)
        writer.record_decision(
            draw_dated_decision(randomness, file=file, decision=retraction, decided_at=later_at)
        )
        writer.record_decision(
            draw_dated_decision(randomness, file=file, decision=record, decided_at=earlier_at)
        )
        assert reader.read_latest_decisions(file) == {record.target_id: retraction}
        assert reader.read_download_candidates() == ()

    def test_the_legacy_retraction_of_no_target_is_left_out(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        record = draw_decision_record(randomness, tier=DecisionTier.NOTIFY)
        writer.record_decision(draw_dated_decision(randomness, file=file, decision=record))
        writer.record_decision(
            draw_dated_decision(randomness, file=file, decision=Retraction(target_id=TargetId("")))
        )
        assert reader.read_latest_decisions(file) == {record.target_id: record}

    def test_a_target_whose_latest_verdict_is_download_is_a_candidate(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        target_id = draw_target_id(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        for tier, decided_at in (
            (DecisionTier.DOWNLOAD, later_at),
            (DecisionTier.CATALOG, earlier_at),
        ):
            record = draw_decision_record(randomness, tier=tier, target_id=target_id)
            writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=record, decided_at=decided_at)
            )
        assert reader.read_download_candidates() == (
            DownloadCandidate(file=file, target_id=target_id),
        )

    @pytest.mark.parametrize("latest_tier", [DecisionTier.CATALOG, DecisionTier.NOTIFY], ids=str)
    def test_a_target_whose_latest_verdict_is_not_download_is_no_candidate(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
        latest_tier: DecisionTier,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        target_id = draw_target_id(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        for tier, decided_at in ((latest_tier, later_at), (DecisionTier.DOWNLOAD, earlier_at)):
            record = draw_decision_record(randomness, tier=tier, target_id=target_id)
            writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=record, decided_at=decided_at)
            )
        assert reader.read_download_candidates() == ()

    def test_each_file_is_a_candidate_on_its_own_latest_verdict(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
    ) -> None:
        candidate_file, other_file = (
            _draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(2)
        )
        target_id = draw_target_id(randomness)
        earliest_at, earlier_at, latest_at = draw_instants(randomness, count=3)
        for file, tier, decided_at in (
            (other_file, DecisionTier.CATALOG, latest_at),
            (candidate_file, DecisionTier.DOWNLOAD, earlier_at),
            (other_file, DecisionTier.DOWNLOAD, earliest_at),
        ):
            record = draw_decision_record(randomness, tier=tier, target_id=target_id)
            writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=record, decided_at=decided_at)
            )
        assert reader.read_download_candidates() == (
            DownloadCandidate(file=candidate_file, target_id=target_id),
        )

    def test_a_file_s_candidates_come_in_target_id_order(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: DecisionWriter,
        reader: DecisionReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        first_target_id, dropped_target_id, last_target_id = draw_target_ids(randomness, count=3)
        earlier_at, later_at = draw_instants(randomness, count=2)
        for target_id, tier, decided_at in (
            (last_target_id, DecisionTier.DOWNLOAD, earlier_at),
            (dropped_target_id, DecisionTier.CATALOG, later_at),
            (dropped_target_id, DecisionTier.DOWNLOAD, earlier_at),
            (first_target_id, DecisionTier.DOWNLOAD, later_at),
        ):
            record = draw_decision_record(randomness, tier=tier, target_id=target_id)
            writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=record, decided_at=decided_at)
            )
        assert reader.read_download_candidates() == (
            DownloadCandidate(file=file, target_id=first_target_id),
            DownloadCandidate(file=file, target_id=last_target_id),
        )
