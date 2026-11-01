"""The promise of the ``SourcePointReader`` and ``SourcePointWriter`` pair."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import replace
from random import Random

import pytest

from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.application.ports.driven.source_point_reader import SourcePointReader
from p2pwatch.application.ports.driven.source_point_writer import SourcePointWriter
from p2pwatch.domain.file_key import FileKey
from p2pwatch.domain.source import LatestPoint, SourcePoint, SourceRole
from tests.support.domain.observation import draw_file, draw_file_observation
from tests.support.domain.source import (
    draw_point_read_again,
    draw_source_key,
    draw_source_point,
    draw_source_reading,
)
from tests.support.draws import draw_instants


def _draw_observed_file(randomness: Random, *, observation_writer: ObservationWriter) -> FileKey:
    file = draw_file(randomness)
    observation_writer.record_observation(
        draw_file_observation(randomness, file=file, has_media=True)
    )
    return file


def _latest_point(point: SourcePoint) -> LatestPoint:
    return LatestPoint(
        role=point.role,
        observed_at=point.observed_at,
        session_received_bytes=point.reading.session_received_bytes,
    )


def _in_time_order(points: Iterable[LatestPoint]) -> list[LatestPoint]:
    """The port leaves the order of the earlier points unstated."""
    return sorted(points, key=lambda point: point.observed_at)


class SourcePointStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def observation_writer(self) -> ObservationWriter:
        """The writer of the observations of the writer's catalog."""

    @pytest.fixture
    @abstractmethod
    def writer(self) -> SourcePointWriter:
        """The writer of a catalog holding no observation and no source point yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> SourcePointReader:
        """The reader of the writer's catalog."""

    @pytest.mark.parametrize("role", list(SourceRole), ids=str)
    def test_a_point_is_read_back_as_its_source_s_latest(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
        role: SourceRole,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        since, observed_at, before = draw_instants(randomness, count=3)
        point = draw_source_point(
            randomness, file=file, source=source, role=role, observed_at=observed_at
        )
        writer.record_points([point])
        reading = draw_source_reading(randomness, source=source, role=None)
        assert reader.read_latest_point(
            file, reading=reading, since=since, before=before, node_id=point.node_id
        ) == _latest_point(point)
        assert reader.read_earlier_points(source, before=before, node_id=point.node_id) == (
            _latest_point(point),
        )

    def test_a_point_of_a_reading_in_a_passing_state_is_read_back_with_its_carried_role(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        since, observed_at, before = draw_instants(randomness, count=3)
        point = draw_source_point(
            randomness, file=file, source=source, role=SourceRole.QUEUED, observed_at=observed_at
        )
        writer.record_points([replace(point, reading=replace(point.reading, role=None))])
        reading = draw_source_reading(randomness, source=source, role=None)
        assert reader.read_latest_point(
            file, reading=reading, since=since, before=before, node_id=point.node_id
        ) == _latest_point(point)

    def test_the_latest_point_is_the_most_recent_of_the_source_s_variants_not_the_last_recorded(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        earliest_at, earlier_at, later_at, before = draw_instants(randomness, count=4)
        first = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.NOTHING_NEW,
            observed_at=earliest_at,
        )
        latest = draw_point_read_again(randomness, point=first, observed_at=later_at)
        other_variant = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.SENDING,
            observed_at=earlier_at,
            node_id=first.node_id,
        )
        writer.record_points([latest, other_variant, first])
        reading = draw_source_reading(randomness, source=source, role=None)
        assert reader.read_latest_point(
            file, reading=reading, since=earliest_at, before=before, node_id=first.node_id
        ) == _latest_point(latest)

    def test_the_latest_point_is_read_from_since_included_to_before_excluded(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        earlier_at, between_at, later_at = draw_instants(randomness, count=3)
        earlier = draw_source_point(
            randomness, file=file, source=source, role=SourceRole.QUEUED, observed_at=earlier_at
        )
        later = draw_point_read_again(randomness, point=earlier, observed_at=later_at)
        writer.record_points([earlier, later])
        reading = draw_source_reading(randomness, source=source, role=None)
        assert reader.read_latest_point(
            file, reading=reading, since=earlier_at, before=later_at, node_id=earlier.node_id
        ) == _latest_point(earlier)
        assert (
            reader.read_latest_point(
                file, reading=reading, since=between_at, before=later_at, node_id=earlier.node_id
            )
            is None
        )

    def test_a_source_without_identity_is_its_name_among_those_without_one(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        named_at, identified_at, other_named_at, before = draw_instants(randomness, count=4)
        named = draw_source_point(
            randomness, file=file, source=None, role=SourceRole.SENDING, observed_at=named_at
        )
        identified = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.NOTHING_NEW,
            observed_at=identified_at,
            node_id=named.node_id,
            source_name=named.reading.source_name,
        )
        other_named = draw_source_point(
            randomness,
            file=file,
            source=None,
            role=SourceRole.STANDBY,
            observed_at=other_named_at,
            node_id=named.node_id,
        )
        writer.record_points([named, identified, other_named])
        renamed = draw_source_reading(randomness, source=source, role=None)
        same_name = draw_source_reading(
            randomness, source=None, role=None, source_name=named.reading.source_name
        )
        unknown_name = draw_source_reading(randomness, source=None, role=None)
        latest_points = [
            reader.read_latest_point(
                file, reading=reading, since=named_at, before=before, node_id=named.node_id
            )
            for reading in (renamed, same_name, unknown_name)
        ]
        assert latest_points == [_latest_point(identified), _latest_point(named), None]

    def test_the_latest_point_is_this_source_s_on_this_file_by_this_node_only(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file, other_file = (
            _draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(2)
        )
        source = draw_source_key(randomness)
        since, on_other_file_at, of_other_source_at, by_other_node_at, before = draw_instants(
            randomness, count=5
        )
        on_other_file = draw_source_point(
            randomness,
            file=other_file,
            source=source,
            role=SourceRole.SENDING,
            observed_at=on_other_file_at,
        )
        of_other_source = draw_source_point(
            randomness,
            file=file,
            source=draw_source_key(randomness),
            role=SourceRole.QUEUED,
            observed_at=of_other_source_at,
            node_id=on_other_file.node_id,
        )
        by_other_node = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.NOTHING_NEW,
            observed_at=by_other_node_at,
        )
        writer.record_points([on_other_file, of_other_source, by_other_node])
        reading = draw_source_reading(randomness, source=source, role=None)
        latest_points = [
            reader.read_latest_point(
                file, reading=reading, since=since, before=before, node_id=node_id
            )
            for node_id in (on_other_file.node_id, by_other_node.node_id)
        ]
        assert latest_points == [None, _latest_point(by_other_node)]

    def test_the_earlier_points_are_the_latest_of_each_of_the_source_s_variants_before_before(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        earliest_at, earlier_at, later_at, before, latest_at = draw_instants(randomness, count=5)
        first = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.NOTHING_NEW,
            observed_at=earliest_at,
        )
        latest_before = draw_point_read_again(randomness, point=first, observed_at=later_at)
        other_variant = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.STANDBY,
            observed_at=earlier_at,
            node_id=first.node_id,
        )
        at_before = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.QUEUED,
            observed_at=before,
            node_id=first.node_id,
        )
        writer.record_points(
            [
                first,
                latest_before,
                other_variant,
                at_before,
                draw_point_read_again(randomness, point=first, observed_at=latest_at),
            ]
        )
        assert _in_time_order(
            reader.read_earlier_points(source, before=before, node_id=first.node_id)
        ) == [_latest_point(other_variant), _latest_point(latest_before)]

    def test_the_earlier_points_are_the_source_s_on_every_file_by_this_node_only(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file, other_file = (
            _draw_observed_file(randomness, observation_writer=observation_writer) for _ in range(2)
        )
        source = draw_source_key(randomness)
        on_file_at, on_other_file_at, of_other_source_at, by_other_node_at, before = draw_instants(
            randomness, count=5
        )
        on_file = draw_source_point(
            randomness, file=file, source=source, role=SourceRole.SENDING, observed_at=on_file_at
        )
        on_other_file = draw_source_point(
            randomness,
            file=other_file,
            source=source,
            role=SourceRole.QUEUED,
            observed_at=on_other_file_at,
            node_id=on_file.node_id,
        )
        of_other_source = draw_source_point(
            randomness,
            file=file,
            source=draw_source_key(randomness),
            role=SourceRole.QUEUED,
            observed_at=of_other_source_at,
            node_id=on_file.node_id,
        )
        by_other_node = draw_source_point(
            randomness,
            file=file,
            source=source,
            role=SourceRole.NOTHING_NEW,
            observed_at=by_other_node_at,
        )
        writer.record_points([on_file, on_other_file, of_other_source, by_other_node])
        assert _in_time_order(
            reader.read_earlier_points(source, before=before, node_id=on_file.node_id)
        ) == [_latest_point(on_file), _latest_point(on_other_file)]
        assert reader.read_earlier_points(source, before=before, node_id=by_other_node.node_id) == (
            _latest_point(by_other_node),
        )

    def test_a_node_has_points_before_an_instant_when_one_of_its_points_is_observed_before_it(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        writer: SourcePointWriter,
        reader: SourcePointReader,
    ) -> None:
        file = _draw_observed_file(randomness, observation_writer=observation_writer)
        source = draw_source_key(randomness)
        earlier_at, observed_at, later_at = draw_instants(randomness, count=3)
        by_other_node = draw_source_point(
            randomness, file=file, source=source, role=SourceRole.QUEUED, observed_at=earlier_at
        )
        point = draw_source_point(
            randomness, file=file, source=source, role=SourceRole.STANDBY, observed_at=observed_at
        )
        assert not reader.has_points_before(later_at, node_id=point.node_id)
        writer.record_points([by_other_node, point])
        assert [
            reader.has_points_before(observed_at, node_id=point.node_id),
            reader.has_points_before(later_at, node_id=point.node_id),
            reader.has_points_before(observed_at, node_id=by_other_node.node_id),
        ] == [False, True, True]
