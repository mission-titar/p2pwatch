from random import Random

from p2pwatch.domain.observation import FileObservation
from tests.support.domain.observation import draw_file, draw_file_observation
from tests.support.draws import draw_instant, draw_quantity


def _drawn(seed: int, *, has_media: bool) -> FileObservation:
    randomness = Random(seed)
    return draw_file_observation(randomness, file=draw_file(randomness), has_media=has_media)


def test_a_drawn_observation_with_media_has_both_media_fields() -> None:
    reported_file = _drawn(0, has_media=True).reported_file
    assert None not in (reported_file.duration_seconds, reported_file.bitrate_kbps)


def test_a_drawn_observation_without_media_has_neither_media_field() -> None:
    reported_file = _drawn(0, has_media=False).reported_file
    assert (reported_file.duration_seconds, reported_file.bitrate_kbps) == (None, None)


def test_a_drawn_observation_keeps_what_its_test_relates() -> None:
    randomness = Random(0)
    file = draw_file(randomness)
    observed_at = draw_instant(randomness)
    source_count = draw_quantity(randomness)
    observation = draw_file_observation(
        randomness,
        file=file,
        has_media=True,
        observed_at=observed_at,
        filename="Keroro 062A.avi",
        source_count=source_count,
    )
    reported_file = observation.reported_file
    assert (reported_file.file, observation.observed_at) == (file, observed_at)
    assert (reported_file.filename, reported_file.source_count) == ("Keroro 062A.avi", source_count)


def test_the_same_seed_draws_the_same_observation() -> None:
    assert _drawn(7, has_media=True) == _drawn(7, has_media=True)
