"""The promise of the ``ObservationReader`` and ``ObservationWriter`` pair."""

from abc import ABC, abstractmethod
from dataclasses import replace
from random import Random

import pytest

from p2pwatch.application.ports.driven.observation_reader import ObservationReader
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from tests.support.domain.observation import draw_file, draw_file_observation
from tests.support.draws import draw_instants, draw_quantities, draw_quantity, draw_text


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
        earliest, earlier, latest = (
            draw_file_observation(randomness, file=file, has_media=True, observed_at=observed_at)
            for observed_at in draw_instants(randomness, count=3)
        )
        # Recorded between the two others: neither the first nor the last recorded is the latest.
        for observation in (earliest, latest, earlier):
            writer.record_observation(observation)
        assert reader.read_latest_observation(file) == latest

    def test_a_report_seen_again_with_fewer_sources_is_read_at_its_latest_sighting(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        fewer_sources, more_sources = draw_quantities(randomness, count=2)
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

    def test_a_later_report_at_another_size_is_read_at_the_file_s_first_size(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        first, later = (
            draw_file_observation(randomness, file=file, has_media=True, observed_at=observed_at)
            for observed_at in draw_instants(randomness, count=2)
        )
        size_bytes = later.reported_file.size_bytes + 1
        writer.record_observation(first)
        writer.record_observation(
            replace(later, reported_file=replace(later.reported_file, size_bytes=size_bytes))
        )
        assert reader.read_latest_observation(file) == later

    def test_the_best_observation_is_the_most_sourced_though_not_the_latest(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        fewer_sources, more_sources = draw_quantities(randomness, count=2)
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
        source_count = draw_quantity(randomness)
        earliest, earlier, latest = (
            draw_file_observation(
                randomness,
                file=file,
                has_media=True,
                observed_at=observed_at,
                source_count=source_count,
            )
            for observed_at in draw_instants(randomness, count=3)
        )
        # Recorded between the two others: neither the first nor the last recorded is the latest.
        for observation in (earliest, latest, earlier):
            writer.record_observation(observation)
        assert reader.read_best_observation(file) == latest

    def test_the_known_filenames_are_the_file_s_distinct_filenames_sorted(
        self, *, randomness: Random, writer: ObservationWriter, reader: ObservationReader
    ) -> None:
        file = draw_file(randomness)
        smaller, larger = sorted(draw_text(randomness) for _ in range(2))
        # Recorded against their sorted order, so that the order of recording fails it.
        for filename in (larger, smaller, larger):
            writer.record_observation(
                draw_file_observation(randomness, file=file, has_media=True, filename=filename)
            )
        writer.record_observation(
            draw_file_observation(randomness, file=draw_file(randomness), has_media=True)
        )
        assert reader.read_known_filenames(file) == (smaller, larger)
