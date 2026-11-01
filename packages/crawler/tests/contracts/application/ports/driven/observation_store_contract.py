"""The promise of the ``ObservationReader`` and ``ObservationWriter`` pair."""

from abc import ABC, abstractmethod
from dataclasses import replace
from random import Random

import pytest

from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from tests.support.domain.observation import draw_file, draw_file_observation, draw_source_counts
from tests.support.draws import draw_instants


class ObservationStoreContract(ABC):
    @pytest.fixture
    @abstractmethod
    def writer(self) -> ObservationWriter:
        """The writer of a catalog holding no observation yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> ObservationReader:
        """The reader of the writer's catalog."""

    def test_a_file_never_observed_has_no_observation_and_no_filename(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        writer.record_observation(
            draw_file_observation(randomness, file=draw_file(randomness), has_media=True)
        )
        file = draw_file(randomness)
        assert reader.read_latest_observation(file) is None
        assert reader.read_best_observation(file) is None
        assert reader.read_known_filenames(file) == ()

    @pytest.mark.parametrize("has_media", [True, False], ids=["with media", "without media"])
    def test_an_observation_is_read_back_whole(
        self,
        *,
        randomness: Random,
        writer: ObservationWriter,
        reader: ObservationReader,
        has_media: bool,
    ) -> None:
        observation = draw_file_observation(
            randomness, file=draw_file(randomness), has_media=has_media
        )
        writer.record_observation(observation)
        file = observation.reported_file.file
        assert reader.read_latest_observation(file) == observation
        assert reader.read_best_observation(file) == observation
        assert reader.read_known_filenames(file) == (observation.reported_file.filename,)

    def test_the_latest_observation_is_the_most_recent_not_the_last_recorded(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        latest = draw_file_observation(randomness, file=file, has_media=True, observed_at=later_at)
        writer.record_observation(latest)
        writer.record_observation(
            draw_file_observation(randomness, file=file, has_media=True, observed_at=earlier_at)
        )
        assert reader.read_latest_observation(file) == latest

    def test_a_report_seen_again_with_fewer_sources_is_read_at_its_latest_sighting(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        fewer_sources, more_sources = draw_source_counts(randomness, count=2)
        first = draw_file_observation(
            randomness, file=file, has_media=True, observed_at=earlier_at, source_count=more_sources
        )
        seen_again = replace(
            first,
            observed_at=later_at,
            reported_file=replace(first.reported_file, source_count=fewer_sources),
        )
        writer.record_observation(first)
        writer.record_observation(seen_again)
        assert reader.read_latest_observation(file) == seen_again

    def test_the_best_observation_is_the_most_sourced_though_not_the_latest(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        fewer_sources, more_sources = draw_source_counts(randomness, count=2)
        most_sourced = draw_file_observation(
            randomness, file=file, has_media=True, observed_at=earlier_at, source_count=more_sources
        )
        writer.record_observation(most_sourced)
        writer.record_observation(
            draw_file_observation(
                randomness,
                file=file,
                has_media=True,
                observed_at=later_at,
                source_count=fewer_sources,
            )
        )
        assert reader.read_best_observation(file) == most_sourced

    def test_the_best_observation_among_the_most_sourced_is_the_latest(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        earlier = draw_file_observation(
            randomness, file=file, has_media=True, observed_at=earlier_at
        )
        latest = draw_file_observation(
            randomness,
            file=file,
            has_media=True,
            observed_at=later_at,
            source_count=earlier.reported_file.source_count,
        )
        writer.record_observation(latest)
        writer.record_observation(earlier)
        assert reader.read_best_observation(file) == latest

    def test_the_known_filenames_are_the_file_s_distinct_filenames_sorted(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        first = draw_file_observation(randomness, file=file, has_media=True)
        second = draw_file_observation(randomness, file=file, has_media=True)
        writer.record_observation(first)
        writer.record_observation(second)
        writer.record_observation(
            draw_file_observation(
                randomness, file=file, has_media=True, filename=first.reported_file.filename
            )
        )
        writer.record_observation(
            draw_file_observation(randomness, file=draw_file(randomness), has_media=True)
        )
        filenames = {first.reported_file.filename, second.reported_file.filename}
        assert reader.read_known_filenames(file) == tuple(sorted(filenames))
