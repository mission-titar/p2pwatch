"""D5's decision on one useful reading (source points spec, and stage 4's block 35 criteria)."""

from datetime import UTC, datetime, timedelta

import pytest

from p2pwatch.application.source_alerts import FirstUseful, Reappeared, source_alert
from p2pwatch.domain.source import SourceRole
from p2pwatch.ports.driven.source_points import EarlierPoints

_ROUND = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
_AFTER = timedelta(hours=12)
_MICROSECOND = timedelta(microseconds=1)
_NEVER = EarlierPoints(has_useful_point=False, latest_known_at=None)
_NOT_USEFUL = (SourceRole.NOTHING_NEW, SourceRole.STANDBY, SourceRole.UNDETERMINED)


def _useful_until(before_round: timedelta) -> EarlierPoints:
    return EarlierPoints(has_useful_point=True, latest_known_at=_ROUND - before_round)


@pytest.mark.parametrize("role", [SourceRole.QUEUED, SourceRole.SENDING])
def test_a_source_never_useful_turning_useful_is_useful_for_the_first_time(
    role: SourceRole,
) -> None:
    # No earlier point, or only unknown ones: the repository answers the same (D5).
    assert source_alert(role, _NEVER, _ROUND, _AFTER) == FirstUseful()


@pytest.mark.parametrize("role", _NOT_USEFUL)
def test_a_reading_that_is_not_useful_raises_nothing(role: SourceRole) -> None:
    assert source_alert(role, _NEVER, _ROUND, _AFTER) is None
    assert source_alert(role, _useful_until(timedelta(hours=13)), _ROUND, _AFTER) is None


def test_a_source_never_useful_unseen_for_13_hours_is_only_new() -> None:
    earlier = EarlierPoints(has_useful_point=False, latest_known_at=_ROUND - timedelta(hours=13))
    assert source_alert(SourceRole.QUEUED, earlier, _ROUND, _AFTER) == FirstUseful()


def test_a_source_useful_before_and_known_recently_raises_nothing() -> None:
    # A teammate's node, nothing_new at every read, once useful.
    earlier = _useful_until(timedelta(seconds=30))
    assert source_alert(SourceRole.QUEUED, earlier, _ROUND, _AFTER) is None


def test_a_source_known_for_the_last_time_just_over_the_threshold_is_useful_again() -> None:
    earlier = _useful_until(_AFTER + _MICROSECOND)
    alert = source_alert(SourceRole.QUEUED, earlier, _ROUND, _AFTER)
    assert alert == Reappeared(absent_for=_AFTER + _MICROSECOND)


def test_a_source_known_for_the_last_time_exactly_at_the_threshold_raises_nothing() -> None:
    assert source_alert(SourceRole.QUEUED, _useful_until(_AFTER), _ROUND, _AFTER) is None


def test_a_useful_history_without_an_end_raises_nothing() -> None:
    # The repository never answers so; the decision stays silent rather than guess an absence.
    earlier = EarlierPoints(has_useful_point=True, latest_known_at=None)
    assert source_alert(SourceRole.QUEUED, earlier, _ROUND, _AFTER) is None
