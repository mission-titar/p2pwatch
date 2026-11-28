"""``WatchedFunction``: a function as its progress is watched, which stalls after 15 minutes
without progress: the crawl on one channel of a client, or the downloads on a client."""

from dataclasses import dataclass
from datetime import timedelta

from p2pwatch.domain.identifiers import Channel, ClientName

# Above twice the backoff's longest wait (2 x 390 s): a channel refused twice in a row stalls not.
STALL_AFTER = timedelta(minutes=15)


@dataclass(kw_only=True, frozen=True)
class WatchedCrawl:
    """The crawl on one channel of a client, such as amuled's kad, which a search progresses."""

    client_name: ClientName
    channel: Channel


@dataclass(kw_only=True, frozen=True)
class WatchedDownloads:
    """The downloads on a client, such as amuled's, which a download round progresses."""

    client_name: ClientName


# Never a part, which is an external dependency.
type WatchedFunction = WatchedCrawl | WatchedDownloads
