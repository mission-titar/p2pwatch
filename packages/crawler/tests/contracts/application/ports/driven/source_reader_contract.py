"""The promise of ``SourceReader``."""

from abc import ABC, abstractmethod
from dataclasses import replace
from datetime import datetime, timedelta
from random import Random

import pytest

from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.application.ports.driven.source_reader import SourceReader
from p2pwatch.domain.file_key import FileKey, Network
from p2pwatch.domain.identifiers import NodeId
from p2pwatch.domain.known_source import KnownSource
from p2pwatch.domain.sharing_period import PeriodWindow, SharingPeriod
from p2pwatch.domain.source import SourceKey, SourcePoint, SourceRole
from tests.support.domain.observation import draw_observed_file
from tests.support.domain.source import draw_point_read_again, draw_source_key, draw_source_point
from tests.support.draws import draw_instant, draw_instants, draw_quantities, draw_text

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
    node_id: NodeId | None = None,
) -> SourcePoint:
    """A queued point of ``source`` on ``file``, ``source_name`` and ``node_id`` drawn unless
    given."""
    return draw_source_point(
        randomness,
        file=file,
        source=source,
        role=SourceRole.QUEUED,
        observed_at=observed_at,
        node_id=node_id,
        source_name=source_name,
    )


def _unnamed(point: SourcePoint) -> SourcePoint:
    """``point`` of a reading that carried no name."""
    return replace(point, reading=replace(point.reading, source_name=None))


def _window(since: datetime, *, until: datetime) -> PeriodWindow:
    """From ``since`` to ``until``, a gap spanning it, so that no gap cuts a period."""
    return PeriodWindow(since=since, until=until, gap=until - since)


def _period(first: SourcePoint, *, last: SourcePoint, received_bytes: int = 0) -> SharingPeriod:
    """The period of ``first``'s variant from ``first`` to ``last``."""
    reading = first.reading
    return SharingPeriod(
        file=first.file,
        source=reading.source,
        source_name=reading.source_name,
        role=first.role,
        contact_point=None if reading.contact_point is None else reading.contact_point.server,
        connectable=reading.connectable,
        first_seen_at=first.observed_at,
        last_seen_at=last.observed_at,
        received_bytes=received_bytes,
        node_id=first.node_id,
    )


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

    def test_a_period_joins_one_source_s_points_by_one_node_the_latest_started_first(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        (
            since,
            first_at,
            other_at,
            elsewhere_at,
            hashless_at,
            unnamed_at,
            latest_at,
            hashless_again_at,
            until,
        ) = draw_instants(randomness, count=9)
        first = _point(
            randomness, file=file, source=draw_source_key(randomness), observed_at=first_at
        )
        node_id = first.node_id
        drawn_other = _point(
            randomness,
            file=file,
            source=draw_source_key(randomness),
            observed_at=other_at,
            node_id=node_id,
        )
        other_source = replace(drawn_other, reading=replace(drawn_other.reading, connectable=False))
        hashless = _point(
            randomness, file=file, source=None, observed_at=hashless_at, node_id=node_id
        )
        drawn_unnamed = _point(
            randomness, file=file, source=None, observed_at=unnamed_at, node_id=node_id
        )
        unnamed = replace(
            drawn_unnamed,
            reading=replace(
                drawn_unnamed.reading, source_name=None, contact_point=None, connectable=None
            ),
        )
        elsewhere = replace(first, node_id=NodeId(draw_text(randomness)), observed_at=elsewhere_at)
        latest = replace(first, observed_at=latest_at)
        hashless_again = replace(hashless, observed_at=hashless_again_at)
        # Recorded in neither order of the periods, so that an order of insertion fails it.
        source_point_writer.record_points(
            [hashless, first, unnamed, other_source, elsewhere, latest, hashless_again]
        )
        assert reader.read_sharing_periods(file, window=_window(since, until=until)) == (
            _period(unnamed, last=unnamed),
            _period(hashless, last=hashless_again),
            _period(elsewhere, last=elsewhere),
            _period(other_source, last=other_source),
            _period(first, last=latest),
        )

    def test_a_file_no_source_was_read_on_has_no_period(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file, read_file = (
            draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(2)
        )
        since, observed_at, until = draw_instants(randomness, count=3)
        source_point_writer.record_points(
            [
                _point(
                    randomness,
                    file=read_file,
                    source=draw_source_key(randomness),
                    observed_at=observed_at,
                )
            ]
        )
        assert reader.read_sharing_periods(file, window=_window(since, until=until)) == ()

    def test_a_period_holds_the_window_s_points_alone_since_included_until_excluded(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        instants = draw_instants(randomness, count=5)
        before_at, since, inside_at, until, after_at = instants
        point = _point(
            randomness, file=file, source=draw_source_key(randomness), observed_at=before_at
        )
        points = [replace(point, observed_at=at) for at in instants]
        source_point_writer.record_points(points)
        window = PeriodWindow(since=since, until=until, gap=after_at - before_at)
        assert reader.read_sharing_periods(file, window=window) == (
            _period(points[1], last=points[2]),
        )

    def test_a_gap_past_the_window_s_gap_cuts_a_period_and_a_gap_at_it_does_not(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        since, first_at, joined_at = draw_instants(randomness, count=3)
        gap = joined_at - first_at
        cut_at = joined_at + gap + timedelta.resolution
        # A queued source's received bytes stay the same, which is no drop.
        first = _point(
            randomness, file=file, source=draw_source_key(randomness), observed_at=first_at
        )
        joined, cut, last = (
            replace(first, observed_at=at) for at in (joined_at, cut_at, cut_at + gap)
        )
        source_point_writer.record_points([first, joined, cut, last])
        window = PeriodWindow(since=since, until=last.observed_at + gap, gap=gap)
        assert reader.read_sharing_periods(file, window=window) == (
            _period(cut, last=last),
            _period(first, last=joined),
        )

    def test_a_drop_of_the_session_s_received_bytes_cuts_a_period(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        since, *instants, until = draw_instants(randomness, count=6)
        lowest, low, high, highest = draw_quantities(randomness, count=4)
        sending = draw_source_point(
            randomness,
            file=file,
            source=draw_source_key(randomness),
            role=SourceRole.SENDING,
            observed_at=since,
        )
        first, grown, dropped, regrown = (
            draw_point_read_again(
                randomness, point=sending, observed_at=at, session_received_bytes=received_bytes
            )
            for at, received_bytes in zip(instants, (low, highest, lowest, high), strict=True)
        )
        source_point_writer.record_points([first, grown, dropped, regrown])
        assert reader.read_sharing_periods(file, window=_window(since, until=until)) == (
            _period(dropped, last=regrown, received_bytes=high - lowest),
            _period(first, last=grown, received_bytes=highest - low),
        )

    def test_a_change_of_role_or_of_reading_cuts_a_period_even_when_the_variant_comes_back(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        since, *instants, until = draw_instants(randomness, count=7)
        source = draw_source_key(randomness)
        sending = draw_source_point(
            randomness, file=file, source=source, role=SourceRole.SENDING, observed_at=since
        )
        standby = replace(
            sending,
            role=SourceRole.STANDBY,
            reading=replace(sending.reading, role=SourceRole.STANDBY),
        )
        read_otherwise = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.SENDING,
            observed_at=since,
            node_id=sending.node_id,
        )
        # The received bytes grow throughout, the standby reading's included.
        points = [
            draw_point_read_again(
                randomness, point=variant, observed_at=at, session_received_bytes=received_bytes
            )
            for variant, at, received_bytes in zip(
                (sending, standby, sending, read_otherwise, sending),
                instants,
                draw_quantities(randomness, count=5),
                strict=True,
            )
        ]
        source_point_writer.record_points(points)
        assert reader.read_sharing_periods(file, window=_window(since, until=until)) == tuple(
            _period(point, last=point) for point in reversed(points)
        )

    @pytest.mark.parametrize("role", list(SourceRole))
    def test_only_a_sending_period_received_bytes_their_growth_over_it(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        source_point_writer: SourcePointWriter,
        reader: SourceReader,
        role: SourceRole,
    ) -> None:
        file = draw_observed_file(randomness, observation_writer=observation_writer)
        since, *instants, until = draw_instants(randomness, count=5)
        point = draw_source_point(
            randomness, file=file, source=draw_source_key(randomness), role=role, observed_at=since
        )
        first, middle, last = (
            draw_point_read_again(
                randomness, point=point, observed_at=at, session_received_bytes=received_bytes
            )
            for at, received_bytes in zip(
                instants, draw_quantities(randomness, count=3), strict=True
            )
        )
        source_point_writer.record_points([first, middle, last])
        growth = last.reading.session_received_bytes - first.reading.session_received_bytes
        assert reader.read_sharing_periods(file, window=_window(since, until=until)) == (
            _period(first, last=last, received_bytes=growth if role is SourceRole.SENDING else 0),
        )
