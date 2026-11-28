"""``WatchedFunction``: a function as its progress is watched, which stalls after 15 minutes
without progress."""

from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.domain.identifiers import Channel, ClientName

# Above twice the backoff's longest wait (2 x 390 s): a channel refused twice in a row stalls not.
STALL_AFTER = timedelta(minutes=15)


@dataclass(kw_only=True, frozen=True)
class WatchedFunction:
    """A function as its progress is watched: the crawl on one channel of a client, such as
    amuled's kad; never a part, which is an external dependency."""

    client_name: ClientName
    channel: Channel
