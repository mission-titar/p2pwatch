"""The promise of the ``SourcePointReader`` and ``SourcePointWriter`` pair."""

from abc import ABC, abstractmethod
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
