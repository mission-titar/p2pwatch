"""The time limit of each work over one aMule client: the bounds on its turn's path, summed, plus
a margin for what grows with what the node tracks."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.adapters.driven.amule_api.amule_api_client import (
    ED2K,
    START_SPACING,
    kad_word_of,
)
from p2pwatch.domain.identifiers import Channel, Keyword

# The tracked downloads, their sources and an answer's files, which no setting bounds: a
# lost-media node tracks few downloads (the operator, 2026-11-11).
TIME_LIMIT_MARGIN = timedelta(minutes=5)

# One call at its worst, each request bounded: another call's login ahead of it on the lock, its
# own login, its request, then on a refused token the same two again and the request resent.
_REQUESTS_PER_CALL = 6


@dataclass(frozen=True, kw_only=True)
class AmuleWorkTimeLimits:
    """The time limits of the works over one aMule client, ``keywords`` those it searches, each
    once."""

    request_bound: timedelta
    search_budget: timedelta
    notification_timeout: timedelta
    keywords: Sequence[Keyword]

    def of_status_reading(self, *, channel_count: int) -> timedelta:
        """Its two calls, and an alert for the client's rule and for each channel's two."""
        alerts = 1 + 2 * channel_count
        return 2 * self._call + alerts * self.notification_timeout + TIME_LIMIT_MARGIN

    def of_search(self, keyword: Keyword, *, channel: Channel) -> timedelta:
        """Its wait for its start, its start, its polls until the budget is spent, its answer's
        first page."""
        others = [other for other in self.keywords if other != keyword]
        budget, call = self.search_budget, self._call
        if channel == ED2K:
            # One eD2k search at a time on a client: every other keyword's, start to end, first.
            ahead = len(others) * max(START_SPACING, budget + 2 * call)
            path = ahead + START_SPACING + budget + 3 * call
        else:  # Kad, aMule's other channel
            # One start per spacing on a Kad word, so one for each keyword sharing it; a start
            # retried for a budget while Kad holds the word, then polled for another.
            kad_word = kad_word_of(keyword)
            sharing = sum(1 for other in others if kad_word and kad_word_of(other) == kad_word)
            path = (1 + sharing) * START_SPACING + 2 * budget + 4 * call
        return path + TIME_LIMIT_MARGIN

    def of_tracking(self) -> timedelta:
        """Download tracking's or source tracking's: the first page of the client's two lists, and
        one notification."""
        return 2 * self._call + self.notification_timeout + TIME_LIMIT_MARGIN

    @property
    def _call(self) -> timedelta:
        return _REQUESTS_PER_CALL * self.request_bound
