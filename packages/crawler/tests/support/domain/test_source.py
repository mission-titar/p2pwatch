from random import Random

from p2pwatch.domain.source import SourcePoint, SourceRole
from tests.support.domain.observation import draw_file
from tests.support.domain.source import draw_source_key, draw_source_point
from tests.support.draws import draw_instant


def _drawn(seed: int) -> SourcePoint:
    randomness = Random(seed)
    return draw_source_point(
        randomness,
        file=draw_file(randomness),
        source=draw_source_key(randomness),
        role=SourceRole.QUEUED,
        observed_at=draw_instant(randomness),
    )


def test_a_drawn_point_keeps_what_its_test_relates() -> None:
    randomness = Random(0)
    file, source = draw_file(randomness), draw_source_key(randomness)
    observed_at = draw_instant(randomness)
    first = draw_source_point(
        randomness, file=file, source=source, role=SourceRole.SENDING, observed_at=observed_at
    )
    point = draw_source_point(
        randomness,
        file=file,
        source=None,
        role=SourceRole.STANDBY,
        observed_at=observed_at,
        node_id=first.node_id,
        source_name=first.reading.source_name,
    )
    assert (first.reading.source, first.role, first.reading.role) == (
        source,
        SourceRole.SENDING,
        SourceRole.SENDING,
    )
    assert (point.file, point.observed_at, point.node_id) == (file, observed_at, first.node_id)
    assert (point.reading.source, point.reading.source_name) == (None, first.reading.source_name)


def test_the_same_seed_draws_the_same_point() -> None:
    assert _drawn(7) == _drawn(7)
