"""The time limit of each work over one aMule client: the bounds on its turn's path, summed, plus a
margin of 5 minutes."""

from datetime import timedelta

import pytest

from p2pwatch.composition.work_time_limits import TIME_LIMIT_MARGIN, AmuleWorkTimeLimits
from p2pwatch.domain.identifiers import Channel, Keyword

_START_SPACING = timedelta(seconds=60)  # between two starts on eD2k, or on one Kad word
_BUDGET = timedelta(seconds=120)
_NOTIFICATION = timedelta(seconds=5)
# One call to amuleapi at its worst: six requests of 60 s each (a login ahead on the lock, its own
# login, the request, then on a refused token the same two again and the request resent).
_CALL = timedelta(seconds=6 * 60)
_TEN_KEYWORDS = tuple(Keyword(f"keroro {number:02}") for number in range(1, 11))


def _limits(
    *keywords: Keyword,
    request_bound: timedelta = timedelta(seconds=60),
    search_budget: timedelta = _BUDGET,
) -> AmuleWorkTimeLimits:
    return AmuleWorkTimeLimits(
        request_bound=request_bound,
        search_budget=search_budget,
        notification_timeout=_NOTIFICATION,
        keywords=keywords or _TEN_KEYWORDS,
    )


def test_the_status_reading_bounds_its_two_calls_and_an_alert_per_rule() -> None:
    # The client's unreachable alert, then each channel's not connected and not connectable.
    alerts = 1 + 2 * 2

    limit = _limits().of_status_reading(channel_count=2)

    assert limit == 2 * _CALL + alerts * _NOTIFICATION + TIME_LIMIT_MARGIN


def test_an_ed2k_search_waits_for_every_other_keywords_search_on_the_client() -> None:
    # The nine others ahead of it, each from its start to its last poll, the budget past.
    others = 9 * (_BUDGET + 2 * _CALL)
    # Its own: the spacing since the latest start, its start, its polls, its answer's first page.
    own = _START_SPACING + _BUDGET + 3 * _CALL

    limit = _limits().of_search(Keyword("keroro 01"), channel=Channel("ed2k"))

    assert limit == others + own + TIME_LIMIT_MARGIN


def test_an_ed2k_search_ahead_shorter_than_the_spacing_counts_the_spacing() -> None:
    limits = _limits(request_bound=timedelta(seconds=1), search_budget=timedelta(seconds=10))
    call = timedelta(seconds=6)
    own = _START_SPACING + timedelta(seconds=10) + 3 * call

    limit = limits.of_search(Keyword("keroro 01"), channel=Channel("ed2k"))

    assert limit == 9 * _START_SPACING + own + TIME_LIMIT_MARGIN


def test_a_kad_search_waits_a_spacing_for_each_keyword_on_its_kad_word() -> None:
    limits = _limits(Keyword("keroro"), Keyword("Keroro mission"), Keyword("titar"))
    # Its start retried for a budget while Kad holds the word, then its polls for another, a
    # widening and a poll each time, then its answer's first page.
    path = 2 * _BUDGET + 4 * _CALL

    keroro = limits.of_search(Keyword("keroro"), channel=Channel("kad"))
    titar = limits.of_search(Keyword("titar"), channel=Channel("kad"))

    # "keroro" and "Keroro mission" share the Kad word `keroro`; "titar" is alone on its own.
    assert keroro == 2 * _START_SPACING + path + TIME_LIMIT_MARGIN
    assert titar == _START_SPACING + path + TIME_LIMIT_MARGIN


def test_a_kad_search_without_a_kad_word_waits_one_spacing() -> None:
    # Neither has a word of 3 bytes, so neither shares a Kad word with the other.
    limits = _limits(Keyword("ab"), Keyword("ab cd"))

    limit = limits.of_search(Keyword("ab"), channel=Channel("kad"))

    assert limit == _START_SPACING + 2 * _BUDGET + 4 * _CALL + TIME_LIMIT_MARGIN


def test_a_search_on_a_channel_amule_lacks_is_refused() -> None:
    with pytest.raises(ValueError, match="aMule has no channel bittorrent"):
        _limits().of_search(Keyword("keroro 01"), channel=Channel("bittorrent"))


def test_download_and_source_tracking_bound_their_two_calls_and_one_notification() -> None:
    assert _limits().of_tracking() == 2 * _CALL + _NOTIFICATION + TIME_LIMIT_MARGIN
