from p2pwatch.domain.crawler_function import CrawlerFunction
from p2pwatch.domain.crawler_restart_error import CrawlerRestartError


def test_it_reads_as_the_function_lost_and_after_how_many_rebuilds() -> None:
    error = CrawlerRestartError(CrawlerFunction.CRAWL, rebuilds=3)

    assert (str(error), error.function, error.rebuilds) == (
        "the crawl lost after 3 rebuilds",
        CrawlerFunction.CRAWL,
        3,
    )
