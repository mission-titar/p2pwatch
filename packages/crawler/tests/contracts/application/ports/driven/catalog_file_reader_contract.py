"""The promise of ``CatalogFileReader``."""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import replace
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
from p2pwatch.domain.file_history import FileHistory
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.file_target_decision import FileTargetDecision, Retraction
from p2pwatch.domain.identifiers import FileId
from p2pwatch.domain.observation import FileObservation
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


def _counts(
    reader: CatalogFileReader,
    *,
    target_id: TargetId | None = None,
    tier: DecisionTier | None = None,
    search_text: str | None = None,
) -> tuple[int, int]:
    return reader.read_matched_and_total_file_counts(
        target_id=target_id, tier=tier, search_text=search_text
    )


def _file_count_by_tier(
    reader: CatalogFileReader, *, target_id: TargetId | None = None, search_text: str | None = None
) -> Mapping[DecisionTier, int]:
    return reader.read_file_count_by_tier(target_id=target_id, search_text=search_text)


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


def _sorted_files(
    reader: CatalogFileReader, *, sort: CatalogEntrySort, direction: SortDirection
) -> list[FileKey]:
    """Every entry's file, in the listing's order."""
    entries = _page(reader, sort=sort, direction=direction, limit=_EVERY_ENTRY, offset=0)
    return [entry.file for entry in entries]


def _page(
    reader: CatalogFileReader,
    *,
    sort: CatalogEntrySort,
    direction: SortDirection,
    limit: int,
    offset: int,
) -> tuple[CatalogEntry, ...]:
    return reader.read_catalog_entries(
        target_id=None,
        tier=None,
        search_text=None,
        matched_only=False,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )


def _in_order(
    value_by_file: Mapping[FileKey, str | int | datetime], *, direction: SortDirection
) -> list[FileKey]:
    """The files by their value in ``direction``, then by ascending ``file_id``."""
    by_file_id = sorted(value_by_file, key=lambda file: file.file_id)
    return sorted(
        by_file_id, key=value_by_file.__getitem__, reverse=direction is SortDirection.DESC
    )


def _record_by_descending_file_id(
    observation_writer: ObservationWriter, *, observations: Iterable[FileObservation]
) -> None:
    """Records ``observations`` against ``file_id`` order, so that an order of insertion fails the
    tie-break, and those of one file in their order."""
    for observation in sorted(
        observations, key=lambda observation: observation.reported_file.file.file_id, reverse=True
    ):
        observation_writer.record_observation(observation)


def _draw_first_and_latest(
    randomness: Random, *, file: FileKey
) -> tuple[FileObservation, FileObservation]:
    first, latest = (
        draw_file_observation(randomness, file=file, has_media=True, observed_at=observed_at)
        for observed_at in draw_instants(randomness, count=2)
    )
    return first, latest


def _of_file(observation: FileObservation, *, file: FileKey) -> FileObservation:
    """``observation`` made of ``file``: the two files then tie on every value a sort reads."""
    return replace(observation, reported_file=replace(observation.reported_file, file=file))


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

    @pytest.mark.parametrize("direction", list(SortDirection), ids=str)
    @pytest.mark.parametrize(
        "sort", [sort for sort in CatalogEntrySort if sort is not CatalogEntrySort.TIER], ids=str
    )
    def test_a_sort_on_the_observations_orders_on_its_value_then_on_file_id(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogFileReader,
        sort: CatalogEntrySort,
        direction: SortDirection,
    ) -> None:
        files = [draw_file(randomness) for _ in range(10)]
        drawn = [_draw_first_and_latest(randomness, file=file) for file in files[:8]]
        twins = [
            (_of_file(first, file=twin), _of_file(latest, file=twin))
            for (first, latest), twin in zip(drawn[:2], files[8:], strict=True)
        ]
        observations_by_file = {
            first.reported_file.file: (first, latest) for first, latest in (*drawn, *twins)
        }
        _record_by_descending_file_id(
            observation_writer,
            observations=(
                observation for pair in observations_by_file.values() for observation in pair
            ),
        )
        value_by_file_by_sort: dict[CatalogEntrySort, dict[FileKey, str | int | datetime]] = {
            CatalogEntrySort.NAME: {
                file: latest.reported_file.filename
                for file, (_, latest) in observations_by_file.items()
            },
            CatalogEntrySort.SIZE: {
                file: first.reported_file.size_bytes
                for file, (first, _) in observations_by_file.items()
            },
            CatalogEntrySort.SOURCES: {
                file: latest.reported_file.source_count
                for file, (_, latest) in observations_by_file.items()
            },
            CatalogEntrySort.LATEST_SEEN: {
                file: latest.observed_at for file, (_, latest) in observations_by_file.items()
            },
        }
        assert _sorted_files(reader, sort=sort, direction=direction) == _in_order(
            value_by_file_by_sort[sort], direction=direction
        )

    @pytest.mark.parametrize("direction", list(SortDirection), ids=str)
    def test_the_tier_sort_orders_on_the_strongest_current_tier_then_on_file_id(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
        direction: SortDirection,
    ) -> None:
        files = [draw_file(randomness) for _ in range(7)]
        _record_by_descending_file_id(
            observation_writer,
            observations=(
                draw_file_observation(randomness, file=file, has_media=True) for file in files
            ),
        )
        undecided, also_undecided, catalogued, retracted, notified, superseded, downloaded = files
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        earlier_at, later_at = draw_instants(randomness, count=2)
        decided = (
            (catalogued, DecisionTier.CATALOG, target_id, None),
            (retracted, DecisionTier.CATALOG, target_id, None),
            (retracted, DecisionTier.DOWNLOAD, other_target_id, earlier_at),
            (notified, DecisionTier.CATALOG, target_id, None),
            (notified, DecisionTier.NOTIFY, other_target_id, None),
            (superseded, DecisionTier.DOWNLOAD, target_id, earlier_at),
            (superseded, DecisionTier.NOTIFY, target_id, later_at),
            (downloaded, DecisionTier.NOTIFY, target_id, None),
            (downloaded, DecisionTier.DOWNLOAD, other_target_id, None),
        )
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=(
                *(
                    (
                        file,
                        draw_decision_record(randomness, tier=tier, target_id=decided_target_id),
                        decided_at,
                    )
                    for file, tier, decided_target_id, decided_at in decided
                ),
                (retracted, Retraction(target_id=other_target_id), later_at),
            ),
        )
        strongest_by_file = {
            undecided: None,
            also_undecided: None,
            catalogued: DecisionTier.CATALOG,
            retracted: DecisionTier.CATALOG,
            notified: DecisionTier.NOTIFY,
            superseded: DecisionTier.NOTIFY,
            downloaded: DecisionTier.DOWNLOAD,
        }
        # A file without a current decision sorts below every rank.
        rank_by_file = {
            file: -1 if tier is None else tier.rank for file, tier in strongest_by_file.items()
        }
        assert _sorted_files(reader, sort=CatalogEntrySort.TIER, direction=direction) == _in_order(
            rank_by_file, direction=direction
        )

    def test_a_page_reads_at_most_its_limit_of_the_sorted_entries_from_its_offset(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogFileReader,
    ) -> None:
        for _ in range(7):
            draw_observed_file(randomness, observation_writer=observation_writer)
        every_entry, *pages = (
            _page(
                reader,
                sort=CatalogEntrySort.LATEST_SEEN,
                direction=SortDirection.DESC,
                limit=limit,
                offset=offset,
            )
            for limit, offset in ((_EVERY_ENTRY, 0), (3, 0), (3, 3), (3, 6), (3, 7))
        )
        assert len(every_entry) == 7
        assert pages == [every_entry[:3], every_entry[3:6], every_entry[6:], ()]

    def test_an_empty_catalog_counts_no_file_and_no_tier(
        self, *, reader: CatalogFileReader
    ) -> None:
        assert (_counts(reader), _file_count_by_tier(reader)) == ((0, 0), {})

    def test_the_counts_count_each_file_once_matched_when_it_holds_a_current_decision(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        whole_episode, catalogued, legacy, retracted, undecided = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(5)
        )
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        downloaded, notified, catalog, still_notified, withdrawn = (
            draw_decision_record(randomness, tier=tier, target_id=decided_target_id)
            for tier, decided_target_id in (
                (DecisionTier.DOWNLOAD, target_id),
                (DecisionTier.NOTIFY, other_target_id),
                (DecisionTier.CATALOG, target_id),
                (DecisionTier.NOTIFY, target_id),
                (DecisionTier.DOWNLOAD, target_id),
            )
        )
        earlier_at, later_at = draw_instants(randomness, count=2)
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=(
                (whole_episode, downloaded, None),
                (whole_episode, notified, None),
                (catalogued, catalog, None),
                (legacy, still_notified, earlier_at),
                (legacy, Retraction(target_id=TargetId("")), later_at),
                (retracted, withdrawn, earlier_at),
                (retracted, Retraction(target_id=target_id), later_at),
            ),
        )
        assert _counts(reader) == (3, 5)

    def test_a_tier_counts_each_file_holding_a_current_decision_of_it_once_or_is_absent(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        both_tiers, downloaded_twice, superseded, retracted, legacy, undecided = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(6)
        )
        target_id, other_target_id = draw_target_ids(randomness, count=2)
        notified, downloaded, downloaded_first, downloaded_second, outdated, superseding = (
            draw_decision_record(randomness, tier=tier, target_id=decided_target_id)
            for tier, decided_target_id in (
                (DecisionTier.NOTIFY, target_id),
                (DecisionTier.DOWNLOAD, other_target_id),
                (DecisionTier.DOWNLOAD, target_id),
                (DecisionTier.DOWNLOAD, other_target_id),
                (DecisionTier.CATALOG, target_id),
                (DecisionTier.DOWNLOAD, target_id),
            )
        )
        withdrawn, still_notified = (
            draw_decision_record(randomness, tier=tier, target_id=target_id)
            for tier in (DecisionTier.CATALOG, DecisionTier.NOTIFY)
        )
        earlier_at, later_at = draw_instants(randomness, count=2)
        _record_decisions(
            randomness,
            decision_writer=decision_writer,
            decisions=(
                (both_tiers, notified, None),
                (both_tiers, downloaded, None),
                (downloaded_twice, downloaded_first, None),
                (downloaded_twice, downloaded_second, None),
                (superseded, outdated, earlier_at),
                (superseded, superseding, later_at),
                (retracted, withdrawn, earlier_at),
                (retracted, Retraction(target_id=target_id), later_at),
                (legacy, still_notified, earlier_at),
                (legacy, Retraction(target_id=TargetId("")), later_at),
            ),
        )
        file_count_by_tier = _file_count_by_tier(reader)
        assert file_count_by_tier == {DecisionTier.DOWNLOAD: 3, DecisionTier.NOTIFY: 2}
        # A `StrEnum` member equals its text: only its type tells the tier from a bare string.
        assert all(type(tier) is DecisionTier for tier in file_count_by_tier)

    def test_the_counts_read_the_files_passing_the_filters(
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
        passing, undecided, catalogued, unnamed, elsewhere = (
            draw_observed_file(randomness, observation_writer=observation_writer, filename=filename)
            for filename in (holding, holding, holding, draw_text(randomness), holding)
        )
        for decided_file, tier, decided_target_id in (
            (passing, DecisionTier.DOWNLOAD, target_id),
            (passing, DecisionTier.CATALOG, other_target_id),
            (catalogued, DecisionTier.CATALOG, target_id),
            (unnamed, DecisionTier.NOTIFY, target_id),
            (elsewhere, DecisionTier.DOWNLOAD, other_target_id),
        ):
            record = draw_decision_record(randomness, tier=tier, target_id=decided_target_id)
            decision_writer.record_decision(
                draw_dated_decision(randomness, file=decided_file, decision=record)
            )
        assert (
            _counts(reader, target_id=target_id),
            _counts(reader, tier=DecisionTier.DOWNLOAD),
            _counts(reader, search_text=search_text),
            _counts(
                reader, target_id=target_id, tier=DecisionTier.DOWNLOAD, search_text=search_text
            ),
        ) == ((2, 2), (2, 2), (3, 4), (1, 1))
        assert (
            _file_count_by_tier(reader, target_id=target_id),
            _file_count_by_tier(reader, search_text=search_text),
            _file_count_by_tier(reader, target_id=target_id, search_text=search_text),
        ) == (
            # A file passing the target counts under the tiers of its other targets too.
            {DecisionTier.DOWNLOAD: 1, DecisionTier.CATALOG: 1, DecisionTier.NOTIFY: 1},
            {DecisionTier.DOWNLOAD: 2, DecisionTier.CATALOG: 2},
            {DecisionTier.DOWNLOAD: 1, DecisionTier.CATALOG: 1},
        )

    def test_a_history_holds_the_first_size_the_interval_s_observations_and_the_latest_of_all(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogFileReader,
    ) -> None:
        file = draw_file(randomness)
        before_at, since, inside_at, until, after_at = draw_instants(randomness, count=5)
        shared_filename = draw_text(randomness)
        first, at_since, inside, at_until, latest = (
            draw_file_observation(
                randomness,
                file=file,
                has_media=has_media,
                observed_at=observed_at,
                filename=filename,
            )
            for has_media, observed_at, filename in (
                (True, before_at, None),
                (False, since, None),
                (True, inside_at, shared_filename),
                (True, until, shared_filename),
                (True, after_at, None),
            )
        )
        for observation in (first, latest, inside, at_until, at_since):
            observation_writer.record_observation(observation)
        filenames = {
            observation.reported_file.filename
            for observation in (first, at_since, inside, at_until, latest)
        }
        assert reader.read_file_history(file.file_id, since=since, until=until) == FileHistory(
            file=file,
            size_bytes=first.reported_file.size_bytes,
            observations=(at_since, inside),
            latest_observation=latest,
            decisions=(),
            known_filenames=tuple(sorted(filenames)),
        )

    def test_a_history_holds_the_current_decision_of_each_target_in_target_order(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        superseded_target_id, notified_target_id, catalogued_target_id, retracted_target_id = (
            draw_target_ids(randomness, count=4)
        )
        earlier_at, later_at = draw_instants(randomness, count=2)
        records = tuple(
            draw_decision_record(randomness, tier=tier, target_id=target_id)
            for tier, target_id in (
                (DecisionTier.DOWNLOAD, superseded_target_id),
                (DecisionTier.NOTIFY, notified_target_id),
                (DecisionTier.CATALOG, catalogued_target_id),
            )
        )
        current = tuple(
            draw_dated_decision(randomness, file=file, decision=record, decided_at=decided_at)
            for record, decided_at in zip(records, (later_at, None, None), strict=True)
        )
        outdated, withdrawn, retraction = (
            draw_dated_decision(randomness, file=file, decision=decision, decided_at=decided_at)
            for decision, decided_at in (
                (
                    draw_decision_record(
                        randomness, tier=DecisionTier.NOTIFY, target_id=superseded_target_id
                    ),
                    earlier_at,
                ),
                (
                    draw_decision_record(
                        randomness, tier=DecisionTier.DOWNLOAD, target_id=retracted_target_id
                    ),
                    earlier_at,
                ),
                (Retraction(target_id=retracted_target_id), later_at),
            )
        )
        for dated_decision in (retraction, withdrawn, *reversed(current), outdated):
            decision_writer.record_decision(dated_decision)
        since, until = draw_instants(randomness, count=2)
        file_history = reader.read_file_history(file.file_id, since=since, until=until)
        assert file_history is not None
        assert file_history.decisions == current
        # A `StrEnum` member equals its text: only `is` tells the tier from a bare string.
        assert all(
            dated_decision.decision.tier is record.tier
            for dated_decision, record in zip(file_history.decisions, records, strict=True)
        )

    def test_a_history_leaves_out_the_legacy_retraction_of_no_target(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        decision_writer: DecisionWriter,
        reader: CatalogFileReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        earlier_at, later_at = draw_instants(randomness, count=2)
        record = draw_decision_record(randomness, tier=DecisionTier.NOTIFY)
        decided, legacy = (
            draw_dated_decision(randomness, file=file, decision=decision, decided_at=decided_at)
            for decision, decided_at in (
                (record, earlier_at),
                (Retraction(target_id=TargetId("")), later_at),
            )
        )
        for dated_decision in (decided, legacy):
            decision_writer.record_decision(dated_decision)
        file_history = reader.read_file_history(file.file_id, since=earlier_at, until=later_at)
        assert file_history is not None
        assert file_history.decisions == (decided,)

    def test_the_history_of_a_file_the_catalog_does_not_hold_is_none(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogFileReader,
    ) -> None:
        held = draw_observed_file(randomness, observation_writer=observation_writer)
        since, until = draw_instants(randomness, count=2)
        # A file is read by its id: the bytes of a held file's native id are no file's.
        for file_id in (draw_file(randomness).file_id, FileId(bytes.fromhex(held.native_id))):
            assert reader.read_file_history(file_id, since=since, until=until) is None
