"""Each work's time limit over one aMule client: the bounds on its turn's path, summed, plus an
allowance for what grows with live counts no setting bounds (spec v5 lot 4, D4)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.adapters.driven.amule_api.amule_api_client import (
    ED2K,
    KAD,
    START_SPACING,
    kad_word_of,
)
from p2pwatch.domain.identifiers import Channel, Keyword

# The tracked downloads, their sources and the files of an answer: a lost-media node tracks few
# downloads, so a fixed allowance covers them (the operator, 2026-11-11).
TIME_LIMIT_ALLOWANCE = timedelta(minutes=5)

# A call's own login, its request, a re-login and a resend on a 401, and two waits on the login
# lock, each for another call's login.
_REQUESTS_PER_CALL = 6


@dataclass(frozen=True, kw_only=True)
class AmuleTurnTimeLimits:
    """The time limits of the works over one aMule client, ``keywords`` every search work's."""

    request_bound: timedelta
    search_budget: timedelta
    notification_timeout: timedelta
    keywords: Sequence[Keyword]

    def of_status_reading(self, *, channel_count: int) -> timedelta:
        """Its two calls, and a notification for the client's condition and each channel's two."""
        notifications = 1 + 2 * channel_count
        return 2 * self._call + notifications * self.notification_timeout + TIME_LIMIT_ALLOWANCE

    def of_search(self, keyword: Keyword, *, channel: Channel) -> timedelta:
        """Its wait for the start, the start, the polls until the budget's last, the answer's
        first page."""
        others = [other for other in self.keywords if other != keyword]
        budget, call = self.search_budget, self._call
        if channel == ED2K:
            # Every other keyword's search ahead on the client's lock, from its start to its end.
            queue = len(others) * max(START_SPACING, budget + 2 * call)
            path = queue + START_SPACING + budget + 3 * call
        elif channel == KAD:
            # A slot per keyword on its Kad word; a held Kad word retried for one budget, then
            # polled for another, a widening before each poll's sleep.
            word = kad_word_of(keyword)
            sharing = sum(1 for other in others if word is not None and kad_word_of(other) == word)
            path = (1 + sharing) * START_SPACING + 2 * budget + 4 * call
        else:
            raise ValueError(f"no time limit for a search on {channel}")
        return path + TIME_LIMIT_ALLOWANCE

    def of_tracking(self) -> timedelta:
        """Download tracking's or source tracking's: the first page of the client's two lists and
        one notification."""
        return 2 * self._call + self.notification_timeout + TIME_LIMIT_ALLOWANCE

    @property
    def _call(self) -> timedelta:
        return _REQUESTS_PER_CALL * self.request_bound
