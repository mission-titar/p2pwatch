from random import Random

from p2pwatch.domain.observation import FileObservation
from tests.support.domain.observation import (
    draw_file,
    draw_file_observation,
    draw_source_counts,
)
from tests.support.draws import draw_instant

_SEEDS = range(1000)


def _drawn(seed: int) -> FileObservation:
    randomness = Random(seed)
    return draw_file_observation(randomness, file=draw_file(randomness), has_media=True)


def test_the_texts_of_a_drawn_observation_differ() -> None:
    for observation in map(_drawn, _SEEDS):
        reported_file = observation.reported_file
        texts = (
            reported_file.file.native_id,
            reported_file.filename,
            reported_file.keyword,
            reported_file.raw_metadata.text,
            observation.node_id,
        )
        assert len(set(texts)) == len(texts), texts


def test_the_quantities_of_a_drawn_observation_differ() -> None:
    for observation in map(_drawn, _SEEDS):
        reported_file = observation.reported_file
        quantities = (
            reported_file.size_bytes,
            reported_file.source_count,
            reported_file.duration_seconds,
            reported_file.bitrate_kbps,
        )
        assert None not in quantities
        assert len(set(quantities)) == len(quantities), quantities


def test_a_drawn_observation_without_media_has_neither_media_field() -> None:
    randomness = Random(0)
    reported_file = draw_file_observation(
        randomness, file=draw_file(randomness), has_media=False
    ).reported_file
    assert (reported_file.duration_seconds, reported_file.bitrate_kbps) == (None, None)


def test_a_drawn_observation_keeps_what_its_test_relates() -> None:
    randomness = Random(0)
    file = draw_file(randomness)
    observed_at = draw_instant(randomness)
    observation = draw_file_observation(
        randomness,
        file=file,
        has_media=True,
        observed_at=observed_at,
        filename="Keroro 062A.avi",
        source_count=draw_source_counts(randomness, count=1)[0],
    )
    assert (observation.reported_file.file, observation.observed_at) == (file, observed_at)
    assert observation.reported_file.filename == "Keroro 062A.avi"


def test_a_related_filename_or_source_count_stays_apart_from_the_other_fields() -> None:
    for seed in _SEEDS:
        randomness = Random(seed)
        other = _drawn(seed + len(_SEEDS))
        observation = draw_file_observation(
            randomness,
            file=other.reported_file.file,
            has_media=True,
            filename=other.reported_file.filename,
            source_count=other.reported_file.source_count,
        )
        reported_file = observation.reported_file
        assert reported_file.filename not in {reported_file.keyword, observation.node_id}
        assert reported_file.source_count not in {
            reported_file.size_bytes,
            reported_file.duration_seconds,
            reported_file.bitrate_kbps,
        }


def test_drawn_source_counts_are_distinct_and_ascending() -> None:
    for seed in _SEEDS:
        fewer, more = draw_source_counts(Random(seed), count=2)
        assert fewer < more


def test_the_same_seed_draws_the_same_observation() -> None:
    assert _drawn(7) == _drawn(7)
