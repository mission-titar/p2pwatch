"""The promise of ``CatalogScanReader``."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import replace
from random import Random

import pytest

from p2pwatch.application.ports.driven.catalog_scan_reader import CatalogScanReader
from p2pwatch.application.ports.driven.observation_writer import ObservationWriter
from p2pwatch.domain.observation import FileObservation
from tests.support.domain.observation import draw_file, draw_file_observation
from tests.support.draws import draw_instants, draw_quantities


def _by_file(observations: Iterable[FileObservation]) -> list[FileObservation]:
    """The port leaves the order of the observations unstated."""
    return sorted(observations, key=lambda observation: observation.reported_file.file.native_id)


class CatalogScanReaderContract(ABC):
    @pytest.fixture
    @abstractmethod
    def observation_writer(self) -> ObservationWriter:
        """The writer of the observations of a catalog holding none yet."""

    @pytest.fixture
    @abstractmethod
    def reader(self) -> CatalogScanReader:
        """The reader of the observation writer's catalog."""

    def test_an_empty_catalog_has_no_file_and_no_observation(
        self, *, reader: CatalogScanReader
    ) -> None:
        assert reader.read_file_count() == 0
        assert list(reader.iter_latest_observations()) == []

    @pytest.mark.parametrize("has_media", [True, False], ids=["with media", "without media"])
    def test_each_file_s_observation_is_read_back_whole(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogScanReader,
        has_media: bool,
    ) -> None:
        observations = [
            draw_file_observation(randomness, file=draw_file(randomness), has_media=has_media)
            for _ in range(2)
        ]
        for observation in observations:
            observation_writer.record_observation(observation)
        assert _by_file(reader.iter_latest_observations()) == _by_file(observations)

    def test_a_file_s_latest_observation_is_the_most_recent_not_the_last_recorded(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogScanReader,
    ) -> None:
        file = draw_file(randomness)
        earlier_at, later_at = draw_instants(randomness, count=2)
        latest = draw_file_observation(randomness, file=file, has_media=True, observed_at=later_at)
        observation_writer.record_observation(latest)
        observation_writer.record_observation(
            draw_file_observation(randomness, file=file, has_media=True, observed_at=earlier_at)
        )
        assert list(reader.iter_latest_observations()) == [latest]

    def test_a_report_seen_again_with_fewer_sources_is_read_at_its_latest_sighting(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogScanReader,
    ) -> None:
        earlier_at, later_at = draw_instants(randomness, count=2)
        fewer_sources, more_sources = draw_quantities(randomness, count=2)
        first = draw_file_observation(
            randomness,
            file=draw_file(randomness),
            has_media=True,
            observed_at=earlier_at,
            source_count=more_sources,
        )
        seen_again = replace(
            first,
            observed_at=later_at,
            reported_file=replace(first.reported_file, source_count=fewer_sources),
        )
        observation_writer.record_observation(first)
        observation_writer.record_observation(seen_again)
        assert list(reader.iter_latest_observations()) == [seen_again]

    def test_the_file_count_counts_files_not_observations(
        self,
        *,
        randomness: Random,
        observation_writer: ObservationWriter,
        reader: CatalogScanReader,
    ) -> None:
        file, other_file = draw_file(randomness), draw_file(randomness)
        for observed_file in (file, file, other_file):
            observation_writer.record_observation(
                draw_file_observation(randomness, file=observed_file, has_media=True)
            )
        assert reader.read_file_count() == 2
