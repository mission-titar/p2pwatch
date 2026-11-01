"""The promise of ``CatalogFileReader``."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from random import Random

import pytest

from catalog_matching.domain.decision_tier import DecisionTier
from catalog_matching.domain.engine import DecisionRecord
from catalog_matching.domain.identifiers import TargetId
from p2pwatch.application.ports.driven.catalog_file_reader import CatalogFileReader
from p2pwatch.application.ports.driven.decision_writer import DecisionWriter
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.domain.catalog_entry import CatalogEntry, CatalogEntrySort, SortDirection
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction
from tests.support.domain.file_target_decision import (
    draw_dated_decision,
    draw_decision_record,
    draw_target_id,
    draw_target_ids,
)
from tests.support.domain.observation import draw_file, draw_file_observation, draw_observed_file
from tests.support.draws import draw_instants, draw_text

_EVERY_ENTRY = 100  # past the files any test records


def _entries(
    reader: CatalogFileReader,
    *,
    target_id: TargetId | None = None,
    tier: DecisionTier | None = None,
    search_text: str | None = None,
    matched_only: bool = False,
) -> tuple[CatalogEntry, ...]:
    """Every entry passing the filters, in an order these tests leave unread."""
    return reader.read_catalog_entries(
        target_id=target_id,
        tier=tier,
        search_text=search_text,
        matched_only=matched_only,
        sort=CatalogEntrySort.NAME,
        direction=SortDirection.ASC,
        limit=_EVERY_ENTRY,
        offset=0,
    )


def _decisions_by_file(
    entries: tuple[CatalogEntry, ...],
) -> dict[FileKey, tuple[DecisionRecord, ...]]:
    decisions_by_file = {entry.file: entry.decisions for entry in entries}
    assert len(decisions_by_file) == len(entries), "a file listed twice"
    return decisions_by_file


def _record_decisions(
    randomness: Random,
    *,
    decision_writer: DecisionWriter,
    decisions: Iterable[tuple[FileKey, FileTargetDecision, datetime | None]],
) -> None:
    """Records each decision on its file, at its instant or a drawn one."""
    for file, decision, decided_at in decisions:
        decision_writer.record_decision(
            draw_dated_decision(randomness, file=file, decision=decision, decided_at=decided_at)
        )


def _holding(randomness: Random, *, search_text: str) -> str:
    """A drawn filename holding ``search_text``."""
    return f"{draw_text(randomness)}{search_text}{draw_text(randomness)}"


class CatalogFileReaderContract(ABC):
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
    def reader(self) -> CatalogFileReader:
        """The reader of the writers' catalog."""

    def test_an_entry_holds_its_first_size_its_latest_observation_and_its_decisions_by_target(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        file = draw_file(randomness)
        first, latest = (
            draw_file_observation(randomness, file=file, has_media=True, observed_at=observed_at)
            for observed_at in draw_instants(randomness, count=2)
        )
        for observation in (first, latest):
            observation_writer.record_observation(observation)
        records = tuple(
            draw_decision_record(randomness, tier=tier, target_id=target_id)
            for tier, target_id in zip(
                DecisionTier, draw_target_ids(randomness, count=len(DecisionTier)), strict=True
            )
        )
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=((file, record, None) for record in reversed(records)),
        )
        [entry] = _entries(reader)
        assert entry == CatalogEntry(
            file=file,
            size_bytes=first.reported_file.size_bytes,
            latest_observation=latest,
            decisions=records,
        )
        # A `StrEnum` member equals its text: only `is` tells the tier from a bare string.
        assert all(
            decision.tier is record.tier
            for decision, record in zip(entry.decisions, records, strict=True)
        )

    def test_an_entry_s_latest_observation_is_the_most_recent_not_the_last_recorded(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogFileReader,
    ) -> None:
        file = draw_file(randomness)
        earlier, later = (
            draw_file_observation(randomness, file=file, has_media=True, observed_at=observed_at)
            for observed_at in draw_instants(randomness, count=2)
        )
        for observation in (later, earlier):
            observation_writer.record_observation(observation)
        [entry] = _entries(reader)
        assert entry.latest_observation == later

    @pytest.mark.parametrize(
        "tier", [tier for tier in DecisionTier if tier.identifies_target], ids=str
    )
    def test_the_target_filter_keeps_a_file_holding_a_current_decision_of_it_not_of_catalog(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
        tier: DecisionTier,
    ) -> None:
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        both, other, catalogued, retracted, undecided = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(5)
        )
        on_target, on_other, only_other, catalog, withdrawn = (
            draw_decision_record(randomness, tier=decided_tier, target_id=decided_target_id)
            for decided_tier, decided_target_id in (
                (tier, target_id),
                (DecisionTier.DOWNLOAD, other_target_id),
                (DecisionTier.DOWNLOAD, other_target_id),
                (DecisionTier.CATALOG, target_id),
                (tier, target_id),
            )
        )
        earlier_at, later_at = draw_instants(randomness, count=2)
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=(
                (both, on_target, None),
                (both, on_other, None),
                (other, only_other, None),
                (catalogued, catalog, None),
                (retracted, withdrawn, earlier_at),
                (retracted, Retraction(target_id=target_id), later_at),
            ),
        )
        assert _decisions_by_file(_entries(reader, target_id=target_id)) == {
            both: (on_target, on_other)
        }
        assert _decisions_by_file(_entries(reader, target_id=other_target_id)) == {
            both: (on_target, on_other),
            other: (only_other,),
        }

    @pytest.mark.parametrize("tier", list(DecisionTier), ids=str)
    def test_the_tier_filter_keeps_a_file_holding_a_current_decision_of_that_tier(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
        tier: DecisionTier,
    ) -> None:
        other_tier = next(each for each in DecisionTier if each is not tier)
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        holding, superseded, retracted = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(3)
        )
        held, also_held, outdated, superseding, withdrawn = (
            draw_decision_record(randomness, tier=decided_tier, target_id=decided_target_id)
            for decided_tier, decided_target_id in (
                (tier, target_id),
                (other_tier, other_target_id),
                (tier, target_id),
                (other_tier, target_id),
                (tier, target_id),
            )
        )
        earlier_at, later_at = draw_instants(randomness, count=2)
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=(
                (holding, held, None),
                (holding, also_held, None),
                (superseded, outdated, earlier_at),
                (superseded, superseding, later_at),
                (retracted, withdrawn, earlier_at),
                (retracted, Retraction(target_id=target_id), later_at),
            ),
        )
        assert _decisions_by_file(_entries(reader, tier=tier)) == {holding: (held, also_held)}

    @pytest.mark.parametrize(
        ("search_text", "found_filename", "missed_filename"),
        [
            ("50%", "50%.avi", "50.avi"),
            ("a_b", "a_b.avi", "axb.avi"),
            ("a\\b", "a\\b.avi", "ab.avi"),
            ("ÉCOLE", "école.avi", "écolier.avi"),
            ("ecole", "école.avi", "écolier.avi"),
            ("KERORO", "Keroro 062A.avi", "Kero 062A.avi"),
        ],
        ids=["percent", "underscore", "backslash", "capitals", "no accents", "ascii capitals"],
    )
    def test_the_search_finds_a_filename_holding_the_text_as_typed_case_and_accents_ignored(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogFileReader,
        search_text: str,
        found_filename: str,
        missed_filename: str,
    ) -> None:
        found, missed = (
            draw_observed_file(randomness, observation_writer=observation_writer, filename=filename)
            for filename in (found_filename, missed_filename)
        )
        assert {entry.file for entry in _entries(reader, search_text=search_text)} == {found}

    def test_the_search_reads_a_file_s_latest_filename_only(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogFileReader,
    ) -> None:
        search_text = draw_text(randomness)
        holding, other = _holding(randomness, search_text=search_text), draw_text(randomness)
        renamed_away, renamed_to = draw_file(randomness), draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        for file, filenames in ((renamed_away, (holding, other)), (renamed_to, (other, holding))):
            for filename, observed_at in zip(filenames, (earlier_at, later_at), strict=True):
                observation_writer.record_observation(
                    draw_file_observation(
                        randomness,
                        file=file,
                        has_media=True,
                        observed_at=observed_at,
                        filename=filename,
                    )
                )
        assert {entry.file for entry in _entries(reader, search_text=search_text)} == {renamed_to}

    def test_a_file_passes_the_filters_when_it_passes_each(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        search_text = draw_text(randomness)
        holding = _holding(randomness, search_text=search_text)
        passing, unnamed, notified, elsewhere = (
            draw_observed_file(randomness, observation_writer=observation_writer, filename=filename)
            for filename in (holding, draw_text(randomness), holding, holding)
        )
        for decided_file, tier, decided_target_id in (
            (passing, DecisionTier.DOWNLOAD, target_id),
            (unnamed, DecisionTier.DOWNLOAD, target_id),
            (notified, DecisionTier.NOTIFY, target_id),
            (elsewhere, DecisionTier.DOWNLOAD, other_target_id),
        ):
            record = draw_decision_record(randomness, tier=tier, target_id=decided_target_id)
            decision_writer.record_decision(
                draw_dated_decision(randomness, file=decided_file, decision=record)
            )
        entries = _entries(
            reader, target_id=target_id, tier=DecisionTier.DOWNLOAD, search_text=search_text
        )
        assert {entry.file for entry in entries} == {passing}

    def test_matched_only_keeps_the_files_holding_a_current_decision(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        matched, retracted, undecided = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(3)
        )
        target_id = draw_target_id(randomness)
        record, withdrawn = (
            draw_decision_record(randomness, tier=decided_tier, target_id=target_id)
            for decided_tier in (DecisionTier.CATALOG, DecisionTier.DOWNLOAD)
        )
        earlier_at, later_at = draw_instants(randomness, count=2)
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=(
                (matched, record, None),
                (retracted, withdrawn, earlier_at),
                (retracted, Retraction(target_id=target_id), later_at),
            ),
        )
        assert _decisions_by_file(_entries(reader)) == {
            matched: (record,),
            retracted: (),
            undecided: (),
        }
        assert _decisions_by_file(_entries(reader, matched_only=True)) == {matched: (record,)}

    def test_the_legacy_retraction_of_no_target_is_left_out(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        record = draw_decision_record(randomness, tier=DecisionTier.NOTIFY)
        earlier_at, later_at = draw_instants(randomness, count=2)
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=(
                (file, record, earlier_at),
                (file, Retraction(target_id=TargetId("")), later_at),
            ),
        )
        assert _decisions_by_file(_entries(reader, matched_only=True)) == {file: (record,)}
