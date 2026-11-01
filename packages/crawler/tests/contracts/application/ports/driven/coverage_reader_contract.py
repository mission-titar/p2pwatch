"""The promise of ``CoverageReader``."""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime
from random import Random

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.application.ports.driven.coverage_reader import CoverageReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction
from tests.support.domain.file_target_decision import (
    draw_dated_decision,
    draw_decision_record,
    draw_target_id,
    draw_target_ids,
)
from tests.support.domain.observation import draw_observed_file
from tests.support.draws import draw_instants


def _sorted_tiers(
    coverage: Mapping[TargetId, tuple[DecisionTier, ...]],
) -> dict[TargetId, list[DecisionTier]]:
    """The port leaves the order of a target's tiers unstated."""
    return {target_id: sorted(tiers) for target_id, tiers in coverage.items()}


class CoverageReaderContract(ABC):
    @pytest.fixture
    @abstractmethod
    def observation_writer(self) -> ObservationWriter:
        """The writer of the observations of a catalog holding none yet."""

    @pytest.fixture
    @abstractmethod
    def decision_writer(self) -> DecisionWriter:
        """The writer of the decisions of the observation writer's catalog."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> CoverageReader:
        """The reader of the writers' catalog."""

    def test_a_catalog_without_decisions_covers_no_target(
        self, *, randomness: Random, observation_writer: ObservationWriter, reader: CoverageReader
    ) -> None:
        draw_observed_file(randomness, observation_writer=observation_writer)
        assert reader.read_target_coverage() == {}

    @pytest.mark.parametrize("tier", list(DecisionTier), ids=str)
    def test_a_decision_is_read_back_as_its_target_s_tier(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CoverageReader,
        tier: DecisionTier,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        record = draw_decision_record(randomness, tier=tier)
        decision_writer.record_decision(draw_dated_decision(randomness, file=file, decision=record))
        coverage = reader.read_target_coverage()
        assert coverage == {record.target_id: (tier,)}
        # A `StrEnum` member equals its text: only `is` tells the tier from a bare string.
        assert coverage[record.target_id][0] is tier

    def test_a_target_holds_the_tier_of_each_of_its_files(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CoverageReader,
    ) -> None:
        target_id = draw_target_id(randomness)
        tiers = [DecisionTier.DOWNLOAD, DecisionTier.CATALOG, DecisionTier.DOWNLOAD]
        for tier in tiers:
            file = draw_observed_file(randomness, observation_writer=observation_writer)
            record = draw_decision_record(randomness, tier=tier, target_id=target_id)
            decision_writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=record)
            )
        assert _sorted_tiers(reader.read_target_coverage()) == {target_id: sorted(tiers)}

    def test_a_file_holds_a_tier_in_each_target_it_matches(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CoverageReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        for decided_target_id, tier in (
            (target_id, DecisionTier.DOWNLOAD),
            (other_target_id, DecisionTier.NOTIFY),
        ):
            record = draw_decision_record(randomness, tier=tier, target_id=decided_target_id)
            decision_writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=record)
            )
        assert reader.read_target_coverage() == {
            target_id: (DecisionTier.DOWNLOAD,),
            other_target_id: (DecisionTier.NOTIFY,),
        }

    def test_a_file_s_tier_is_that_of_its_latest_decision_not_the_last_recorded(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CoverageReader,
    ) -> None:
        file, other_file = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(2)
        )
        target_id = draw_target_id(randomness)
        earlier_at, later_at, latest_at = draw_instants(randomness, count=3)
        for decided_file, tier, decided_at in (
            (file, DecisionTier.NOTIFY, later_at),
            (file, DecisionTier.DOWNLOAD, earlier_at),
            (other_file, DecisionTier.CATALOG, latest_at),
        ):
            record = draw_decision_record(randomness, tier=tier, target_id=target_id)
            decision_writer.record_decision(
                draw_dated_decision(
                    randomness, file=decided_file, decision=record, decided_at=decided_at
                )
            )
        assert _sorted_tiers(reader.read_target_coverage()) == {
            target_id: sorted([DecisionTier.NOTIFY, DecisionTier.CATALOG])
        }

    def test_a_target_whose_latest_decision_is_a_retraction_is_left_out(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CoverageReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        retracted_target_id, kept_target_id = draw_target_ids(randomness, count=2)
        earlier_at, later_at = draw_instants(randomness, count=2)
        decisions: tuple[tuple[FileTargetDecision, datetime], ...] = (
            (Retraction(target_id=retracted_target_id), later_at),
            (
                draw_decision_record(
                    randomness, tier=DecisionTier.DOWNLOAD, target_id=retracted_target_id
                ),
                earlier_at,
            ),
            (
                draw_decision_record(
                    randomness, tier=DecisionTier.CATALOG, target_id=kept_target_id
                ),
                earlier_at,
            ),
        )
        for decision, decided_at in decisions:
            decision_writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=decision, decided_at=decided_at)
            )
        assert reader.read_target_coverage() == {kept_target_id: (DecisionTier.CATALOG,)}

    def test_the_legacy_retraction_of_no_target_is_left_out(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CoverageReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        earlier_at, later_at = draw_instants(randomness, count=2)
        record = draw_decision_record(randomness, tier=DecisionTier.NOTIFY)
        decisions: tuple[tuple[FileTargetDecision, datetime], ...] = (
            (record, earlier_at),
            (Retraction(target_id=TargetId("")), later_at),
        )
        for decision, decided_at in decisions:
            decision_writer.record_decision(
                draw_dated_decision(randomness, file=file, decision=decision, decided_at=decided_at)
            )
        assert reader.read_target_coverage() == {record.target_id: (DecisionTier.NOTIFY,)}
