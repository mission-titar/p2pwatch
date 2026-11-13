"""Each work's time limit over one aMule client: the bounds on its turn's path, summed, plus the
allowance for what grows with live counts (spec v5 lot 4, D4)."""

from datetime import timedelta

import pytest

from p2pwatch.composition.turn_time_limits import TIME_LIMIT_ALLOWANCE, AmuleTurnTimeLimits
from p2pwatch.domain.identifiers import Channel, Keyword

_SPACING = timedelta(seconds=60)  # the adapter's start spacing, a network rule
_BUDGET = timedelta(seconds=120)
_NOTIFICATION = timedelta(seconds=5)
# One amuleapi call: four requests of 60 s and two waits of one login each on the login lock.
_CALL = timedelta(seconds=6 * 60)
_KEYWORDS = tuple(Keyword(f"keroro {number:02}") for number in range(1, 11))


def _limits(
    *keywords: Keyword, request_bound: float = 60.0, search_budget: timedelta = _BUDGET
) -> AmuleTurnTimeLimits:
    return AmuleTurnTimeLimits(
        request_bound=timedelta(seconds=request_bound),
        search_budget=search_budget,
        notification_timeout=_NOTIFICATION,
        keywords=keywords or _KEYWORDS,
    )


def test_the_status_reading_bounds_its_two_calls_and_a_notification_per_condition() -> None:
    # The client's unreachable condition, then each channel's two fields.
    notifications = 1 + 2 * 2
    assert _limits().of_status_reading(channel_count=2) == (
        2 * _CALL + notifications * _NOTIFICATION + TIME_LIMIT_ALLOWANCE
    )


def test_an_ed2k_search_waits_through_every_other_keywords_search_on_the_lock() -> None:
    # The nine others, each holding the lock from its start through its last poll.
    queue = 9 * (_BUDGET + 2 * _CALL)
    # Its own: the spacing, the start, the budget's last poll, the answer's first page.
    own = _SPACING + _BUDGET + 3 * _CALL
    limit = _limits().of_search(Keyword("keroro 01"), channel=Channel("ed2k"))
    assert limit == queue + own + TIME_LIMIT_ALLOWANCE


def test_an_ed2k_search_shorter_than_the_spacing_waits_a_spacing_per_other_keyword() -> None:
    call = timedelta(seconds=6)
    limit = _limits(request_bound=1.0, search_budget=timedelta(seconds=10)).of_search(
        Keyword("keroro 01"), channel=Channel("ed2k")
    )
    own = _SPACING + timedelta(seconds=10) + 3 * call
    assert limit == 9 * _SPACING + own + TIME_LIMIT_ALLOWANCE


def test_a_kad_search_waits_a_spacing_per_keyword_sharing_its_kad_word() -> None:
    limits = _limits(Keyword("keroro"), Keyword("Keroro mission"), Keyword("titar"))
    # Its slot, after the other's on `keroro`; a held Kad word retried for one budget, then
    # polled for another, widened between polls; the answer's first page.
    path = 2 * _BUDGET + 4 * _CALL
    assert limits.of_search(Keyword("keroro"), channel=Channel("kad")) == (
        2 * _SPACING + path + TIME_LIMIT_ALLOWANCE
    )
    assert limits.of_search(Keyword("titar"), channel=Channel("kad")) == (
        _SPACING + path + TIME_LIMIT_ALLOWANCE
    )


def test_a_kad_search_without_a_kad_word_waits_its_own_slot_alone() -> None:
    limits = _limits(Keyword("ab"), Keyword("ab cd"))
    assert limits.of_search(Keyword("ab"), channel=Channel("kad")) == (
        _SPACING + 2 * _BUDGET + 4 * _CALL + TIME_LIMIT_ALLOWANCE
    )


def test_a_search_on_a_channel_the_client_lacks_is_refused() -> None:
    with pytest.raises(ValueError, match="no time limit for a search on bittorrent"):
        _limits().of_search(Keyword("keroro 01"), channel=Channel("bittorrent"))


def test_tracking_bounds_the_first_page_of_both_lists_and_one_notification() -> None:
    assert _limits().of_tracking() == 2 * _CALL + _NOTIFICATION + TIME_LIMIT_ALLOWANCE
