"""The promise of ``SourceReader``."""

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime
from random import Random

import pytest

from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.source import SourceKey, SourcePoint, SourceRole
from tests.support.domain.observation import draw_observed_file
from tests.support.domain.source import draw_point_read_again, draw_source_key, draw_source_point
from tests.support.draws import draw_instant, draw_instants, draw_text

_EVERY_SOURCE = 100  # past the sources any test records


def _known_sources(
    reader: SourceReader, *, search_text: str | None = None
) -> tuple[KnownSource, ...]:
    return reader.read_known_sources(search_text=search_text, limit=_EVERY_SOURCE, offset=0)


def _search(reader: SourceReader, *, search_text: str) -> tuple[set[SourceKey], int]:
    """The sources ``search_text`` finds, and how many ``read_source_count`` says it finds."""
    found = {known.source for known in _known_sources(reader, search_text=search_text)}
    return found, reader.read_source_count(search_text=search_text)


def _point(
    randomness: Random,
    *,
    file: FileKey,
    source: SourceKey | None,
    observed_at: datetime,
    source_name: str | None = None,
) -> SourcePoint:
    """A queued point of ``source`` on ``file``, ``source_name`` drawn unless given."""
    return draw_source_point(
        randomness,
        file=file,
        source=source,
        role=SourceRole.QUEUED,
        observed_at=observed_at,
        source_name=source_name,
    )


def _unnamed(point: SourcePoint) -> SourcePoint:
    """``point`` of a reading that carried no name."""
    return replace(point, reading=replace(point.reading, source_name=None))


class SourceReaderContract(ABC):
    @pytest.fixture
    @abstractmethod
    def observation_writer(self) -> ObservationWriter:
        """The writer of the observations of a catalog holding none yet."""

    @pytest.fixture
    @abstractmethod
    def source_point_writer(self) -> SourcePointWriter:
        """The writer of the source points of the observation writer's catalog."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> SourceReader:
        """The reader of the writers' catalog."""

    def test_a_known_source_holds_its_latest_name_its_latest_reading_and_its_file_count(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file, other_file = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(2)
        )
        source = draw_source_key(randomness)
        earliest_at, earlier_at, later_at, latest_at = draw_instants(randomness, count=4)
        latest_named = _point(randomness, file=file, source=source, observed_at=earliest_at)
        earlier_named = _point(randomness, file=other_file, source=source, observed_at=earlier_at)
        unnamed = _unnamed(_point(randomness, file=file, source=source, observed_at=latest_at))
        source_point_writer.record_points(
            [
                unnamed,
                draw_point_read_again(randomness, point=latest_named, observed_at=later_at),
                earlier_named,
                latest_named,
            ]
        )
        assert _known_sources(reader) == (
            KnownSource(
                source=source,
                source_name=latest_named.reading.source_name,
                latest_seen_at=latest_at,
                file_count=2,
            ),
        )

    def test_a_source_never_named_is_known_without_a_name(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        point = _unnamed(
            _point(randomness, file=file, source=source, observed_at=draw_instant(randomness))
        )
        source_point_writer.record_points([point])
        assert _known_sources(reader) == (
            KnownSource(
                source=source, source_name=None, latest_seen_at=point.observed_at, file_count=1
            ),
        )

    def test_the_sources_with_a_user_hash_are_listed_last_seen_first_then_on_source_id(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        sources = [draw_source_key(randomness) for _ in range(4)]
        earlier_at, later_at = draw_instants(randomness, count=2)
        seen_at_by_source = dict(
            zip(sources, (earlier_at, later_at, earlier_at, later_at), strict=True)
        )
        by_source_id = sorted(sources, key=lambda source: source.source_id)
        listed = sorted(by_source_id, key=seen_at_by_source.__getitem__, reverse=True)
        # Against the listed order, so that an order of insertion fails it.
        source_point_writer.record_points(
            [
                _point(randomness, file=file, source=None, observed_at=later_at),
                *(
                    _point(
                        randomness, file=file, source=source, observed_at=seen_at_by_source[source]
                    )
                    for source in reversed(listed)
                ),
            ]
        )
        assert [known.source for known in _known_sources(reader)] == listed
        assert reader.read_source_count(search_text=None) == len(sources)

    def test_a_page_reads_at_most_its_limit_of_the_listed_sources_from_its_offset(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        source_point_writer.record_points(
            [
                _point(randomness, file=file, source=draw_source_key(randomness), observed_at=at)
                for at in draw_instants(randomness, count=7)
            ]
        )
        every_source, *pages = (
            reader.read_known_sources(search_text=None, limit=limit, offset=offset)
            for limit, offset in ((_EVERY_SOURCE, 0), (3, 0), (3, 3), (3, 6), (3, 7))
        )
        assert len(every_source) == 7
        assert pages == [every_source[:3], every_source[3:6], every_source[6:], ()]

    @pytest.mark.parametrize(
        ("search_text", "found_name", "missed_name"),
        [
            ("50%", "50%", "50"),
            ("a_b", "a_b", "axb"),
            ("a\\b", "a\\b", "ab"),
            ("ÉCOLE", "école", "écolier"),
            ("ecole", "école", "écolier"),
            ("KERORO", "Keroro", "Kero"),
        ],
        ids=["percent", "underscore", "backslash", "capitals", "no accents", "ascii capitals"],
    )
    def test_the_search_finds_a_name_holding_the_text_as_typed_case_and_accents_ignored(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
        search_text: str,
        found_name: str,
        missed_name: str,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        found, missed = draw_source_key(randomness), draw_source_key(randomness)
        observed_at = draw_instant(randomness)
        source_point_writer.record_points(
            [
                _point(
                    randomness,
                    file=file,
                    source=source,
                    observed_at=observed_at,
                    source_name=source_name,
                )
                for source, source_name in ((found, found_name), (missed, missed_name))
            ]
        )
        assert _search(reader, search_text=search_text) == ({found}, 1)

    def test_the_search_reads_every_name_a_source_carried_and_lists_what_it_finds_whole(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        search_text = draw_text(randomness)
        holding = f"{draw_text(randomness)}{search_text}{draw_text(randomness)}"
        renamed_away, still_named, other = (draw_source_key(randomness) for _ in range(3))
        earliest_at, earlier_at, latest_at = draw_instants(randomness, count=3)
        renamed_to = _point(randomness, file=file, source=renamed_away, observed_at=latest_at)
        source_point_writer.record_points(
            [
                _point(
                    randomness,
                    file=file,
                    source=still_named,
                    observed_at=earlier_at,
                    source_name=holding,
                ),
                _point(
                    randomness,
                    file=file,
                    source=renamed_away,
                    observed_at=earliest_at,
                    source_name=holding,
                ),
                renamed_to,
                _point(randomness, file=file, source=other, observed_at=latest_at),
                _point(
                    randomness, file=file, source=None, observed_at=latest_at, source_name=holding
                ),
            ]
        )
        assert _known_sources(reader, search_text=search_text) == (
            KnownSource(
                source=renamed_away,
                source_name=renamed_to.reading.source_name,
                latest_seen_at=latest_at,
                file_count=1,
            ),
            KnownSource(
                source=still_named, source_name=holding, latest_seen_at=earlier_at, file_count=1
            ),
        )
        assert reader.read_source_count(search_text=search_text) == 2

    @pytest.mark.parametrize(
        ("search_text", "is_found"),
        [
            ("1f2e1f2e", True),
            ("1F2E1F2E", True),
            ("1f2é1f2é", True),
            ("f2e1f2e1", False),
            ("1f2e%", False),
            ("1f_e", False),
            ("1f2e\\1f2e", False),
        ],
        ids=[
            "start",
            "capitals",
            "accents",
            "past the start",
            "percent",
            "underscore",
            "backslash",
        ],
    )
    def test_the_search_finds_the_start_of_a_user_hash_as_typed_case_and_accents_ignored(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
        search_text: str,
        is_found: bool,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        source = SourceKey(network=Network.ED2K, native_id="1f2e" * 8)
        observed_at = draw_instant(randomness)
        source_point_writer.record_points(
            [
                _point(randomness, file=file, source=each, observed_at=observed_at)
                for each in (source, draw_source_key(randomness))
            ]
        )
        found = {source} if is_found else set()
        assert _search(reader, search_text=search_text) == (found, len(found))
