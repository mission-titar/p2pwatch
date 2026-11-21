"""``CrawlerFunction``: what the crawler exists for, such as the crawl its searches serve."""

from enum import Enum


class CrawlerFunction(Enum):
    """One of the crawler's functions, as the log names it; each work serves one, or none, as the
    status reading."""

    WEBUI = "the webui"
    NOTIFICATIONS = "the notifications"
    CRAWL = "the crawl"
    DOWNLOADS = "the downloads"  # on a node that downloads
