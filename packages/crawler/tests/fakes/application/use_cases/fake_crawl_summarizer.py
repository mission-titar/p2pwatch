from p2pwatch.application.ports.driving.crawl_summarizer import CrawlSummarizer, CrawlSummary


class FakeCrawlSummarizer(CrawlSummarizer):
    """Summarizes the crawl as it is given."""

    def __init__(self, crawl_summary: CrawlSummary) -> None:
        self._crawl_summary = crawl_summary

    def summarize_crawl(self) -> CrawlSummary:
        return self._crawl_summary
