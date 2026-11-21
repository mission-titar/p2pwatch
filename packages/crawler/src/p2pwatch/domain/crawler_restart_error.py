"""The error the crawler stops with so that Docker starts it again whole, which the command line
reports before exiting non-zero."""

from p2pwatch.domain.crawler_function import CrawlerFunction


class CrawlerRestartError(Exception):
    """A function of the crawler, such as the crawl, wholly lost after ``rebuilds`` rebuilds of
    every object serving it: the cause may lie in something shared, which a new process renews."""

    def __init__(self, function: CrawlerFunction, *, rebuilds: int) -> None:
        super().__init__(f"{function.value} lost after {rebuilds} rebuilds")
        self.function = function
        self.rebuilds = rebuilds
